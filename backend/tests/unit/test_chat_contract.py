import pytest

from backend.app.services.answer_renderer import format_inr, render_answer
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
