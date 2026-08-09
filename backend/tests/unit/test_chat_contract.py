from types import SimpleNamespace

import pytest

from backend.app.config import Settings
from backend.app.domain.chat_models import ChatPlan, ChatScope
from backend.app.repositories.store import MemoryStore
from backend.app.services.answer_renderer import format_inr, render_answer
from backend.app.services.chat_answer_service import ChatAnswerService
from backend.app.services.chat_executor import execute_plan
from backend.app.services.chat_planner import plan_question


@pytest.mark.parametrize(
    ("question", "intent"),
    [
        ("How many proposal or RFP emails came in?", "count_category"),
        ("How many were marketing versus actual spam we correctly ignored?", "compare_category_and_skip_reason"),
        ("Show me everything sitting in triage and why.", "list_triage"),
        ("What's our spurious rate so far?", "spurious_rate"),
        ("Which tasks are high priority but low confidence?", "list_priority_confidence"),
        ("How many alliances emails came from resellers versus tech integration partners?", "count_subtypes"),
        ("How many GST refund requests were there?", "count_topic"),
        ("Send an email to all RFP prospects.", "out_of_scope"),
        ("What's the total deal value of all open RFPs?", "sum_deal_value"),
        ("Which threads were updated more than once?", "threads_with_updates"),
    ],
)
def test_required_chat_questions_map_to_allowlisted_intents(question: str, intent: str) -> None:
    assert plan_question(question).intent == intent


def test_refusal_never_claims_an_action() -> None:
    answer, status = render_answer(plan_question("Send an email to the buyer"), {})
    assert status == "refused"
    assert "cannot send" in answer


def test_inr_format_uses_indian_grouping() -> None:
    assert format_inr(34_250_003) == "3,42,50,003"


def test_sample_proposal_versus_marketing_question_is_supported() -> None:
    plan = plan_question("Of the emails I just pasted, how many look like proposals versus marketing?")
    assert plan.intent == "compare_categories"
    assert plan.categories == ["enterprise_rfp", "marketing"]


@pytest.mark.parametrize(
    ("question", "intent"),
    [
        ("Count the tender-related messages in this upload", "count_category"),
        ("Compare sponsorship requests with SEO pitches we discarded", "compare_category_and_skip_reason"),
        ("Why did the system route some messages for manual review?", "list_triage"),
        ("What percentage of processed mail was incorrectly escalated?", "spurious_rate"),
        ("Show urgent work where the routing certainty is poor", "list_priority_confidence"),
        ("Break partnerships down into channel resale and integrations", "count_subtypes"),
        ("Were there any GST refund messages?", "count_topic"),
        ("Please notify Aarti about Meridian Steel", "out_of_scope"),
        ("Add up the value of active tender opportunities", "sum_deal_value"),
        ("Which conversations changed at least twice?", "threads_with_updates"),
        ("Send Aarti an email about the Meridian Steel RFP", "out_of_scope"),
    ],
)
def test_required_chat_families_accept_natural_paraphrases(question: str, intent: str) -> None:
    assert plan_question(question).intent == intent


def seeded_store() -> tuple[MemoryStore, ChatScope]:
    store = MemoryStore()
    batch = "11111111-1111-4111-8111-111111111111"

    def decision(email_id: str, thread_id: str, *, task: dict | None = None, **extra: object) -> dict:
        return {
            "email_id": email_id,
            "thread_id": thread_id,
            "operation": "create" if task else "skip",
            "client_batch_id": batch,
            "run_id": "run-1",
            "task": task,
            "reasoning": extra.pop("reasoning", "Stored routing reason"),
            "topics": extra.pop("topics", []),
            **extra,
        }

    tasks = {
        "t-rfp-valued": {"category": "enterprise_rfp", "priority": "medium", "confidence": 0.91, "deal_value_inr": 2_500_000},
        "t-rfp-null": {"category": "enterprise_rfp", "priority": "high", "confidence": 0.4, "deal_value_inr": None},
        "t-marketing": {"category": "marketing", "priority": "medium", "confidence": 0.88, "deal_value_inr": None},
        "t-triage": {"category": "triage", "priority": "medium", "confidence": 0.42, "deal_value_inr": None},
        "t-reseller": {"category": "alliances", "priority": "medium", "confidence": 0.84, "deal_value_inr": None},
        "t-integration": {"category": "alliances", "priority": "medium", "confidence": 0.86, "deal_value_inr": None},
    }
    store.decisions = {
        "e-rfp-valued": decision("e-rfp-valued", "t-rfp-valued", task=tasks["t-rfp-valued"]),
        "e-rfp-null": decision("e-rfp-null", "t-rfp-null", task=tasks["t-rfp-null"]),
        "e-marketing": decision("e-marketing", "t-marketing", task=tasks["t-marketing"]),
        "e-spam": decision("e-spam", "t-spam", skip_reason="vendor_spam"),
        "e-triage": decision("e-triage", "t-triage", task=tasks["t-triage"], reasoning="Two material asks have different owners"),
        "e-reseller": decision("e-reseller", "t-reseller", task=tasks["t-reseller"], alliance_subtype="reseller"),
        "e-integration": decision("e-integration", "t-integration", task=tasks["t-integration"], alliance_subtype="technology_integration"),
    }
    store.deliveries = [
        {
            "run_id": "run-1",
            "client_batch_id": batch,
            "email_id": row["email_id"],
            "thread_id": row["thread_id"],
            "outcome": row["operation"],
        }
        for row in store.decisions.values()
    ]
    store.threads = {
        thread_id: {
            "thread_id": thread_id,
            "remote_task_id": f"tsk-{thread_id}",
            "current_task_snapshot": task,
        }
        for thread_id, task in tasks.items()
    }
    store.events = [
        {"thread_id": "t-rfp-valued", "event_type": "update", "status": "confirmed"},
        {"thread_id": "t-rfp-valued", "event_type": "update", "status": "confirmed"},
    ]
    store.feedback = {"e-marketing": {"email_id": "e-marketing", "label": "spurious"}}
    return store, ChatScope(type="batch", id=batch)


def test_problem_statement_question_matrix_returns_grounded_supporting_data() -> None:
    store, scope = seeded_store()
    cases = [
        ("How many proposal or RFP emails came in?", {"enterprise_rfp": 2}),
        ("How many were marketing versus actual spam we correctly ignored?", {"marketing": 1, "skipped_marketing_lookalike_spam": 1}),
        ("Show me everything sitting in triage and why.", {"triage_count": 1, "triage_task_ids": ["tsk-t-triage"]}),
        ("What's our spurious rate so far?", {"spurious_count": 1, "processed": 7, "spurious_rate": 0.1429}),
        ("Which tasks are high priority but low confidence?", {"count": 1}),
        ("How many alliances emails came from resellers versus tech integration partners?", {"alliances": 2}),
        ("How many GST refund requests were there?", {"gst_refund_count": 0}),
        ("Send an email to all RFP prospects.", {}),
        ("What's the total deal value of all open RFPs?", {"total_deal_value_inr": 2_500_000, "rfps_with_no_stated_value": 1}),
        ("Which threads were updated more than once?", {"threads_updated_multiple_times": ["t-rfp-valued"]}),
    ]
    for question, expected in cases:
        plan = plan_question(question)
        data = execute_plan(store, plan, scope)
        answer, status = render_answer(plan, data)
        assert answer
        assert status in {"answered", "refused"}
        for key, value in expected.items():
            assert data[key] == value


def test_gemini_can_only_rephrase_without_changing_numbers() -> None:
    service = ChatAnswerService(Settings())
    plan = ChatPlan(intent="count_category", categories=["enterprise_rfp"])
    draft = "There are 3 enterprise_rfp email decisions in this scope."
    service._client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **_: SimpleNamespace(parsed={"answer": "This scope contains 3 enterprise RFP decisions."})))
    assert service.phrase(plan, {"enterprise_rfp": 3}, draft) == "This scope contains 3 enterprise RFP decisions."

    service._client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **_: SimpleNamespace(parsed={"answer": "This scope contains 4 enterprise RFP decisions."})))
    assert service.phrase(plan, {"enterprise_rfp": 3}, draft) == draft
