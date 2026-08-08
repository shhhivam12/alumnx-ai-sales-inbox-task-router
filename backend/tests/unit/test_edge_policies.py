from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app.domain.email_models import EmailMessage
from backend.app.domain.enums import Actionability, AssigneeId, Category, Operation, SkipReason
from backend.app.domain.extraction_models import (
    AmountMention,
    DeadlineMention,
    ExtractionResult,
    FieldChange,
    Intent,
    ReplyChanges,
)
from backend.app.domain.routing_policy import route_email
from backend.app.main import app
from backend.app.services.email_normalizer import normalize_email
from backend.app.services.suppression import deterministic_suppression


RECEIVED = datetime(2026, 8, 9, 9, tzinfo=timezone.utc)


def email(body: str, *, subject: str = "Request", index: int = 0, reply: bool = False) -> EmailMessage:
    return EmailMessage(
        email_id=f"edge-{uuid4().hex}", thread_id=f"thread-{uuid4().hex}", message_index=index,
        from_name="Buyer", from_email="buyer@example.com", to="sales@example.com", cc=[],
        subject=subject, body=body, received_at=RECEIVED, attachments=[], is_reply=reply,
    )


def extraction(intent: Intent, *, value: int | None = None, deadline_hours: int | None = None) -> ExtractionResult:
    amounts = [] if value is None else [AmountMention(value_inr=value, original_currency="INR", original_text=str(value), role="deal_budget", evidence=str(value))]
    deadlines = [] if deadline_hours is None else [DeadlineMention(resolved_at=RECEIVED + timedelta(hours=deadline_hours), role="submission", evidence="deadline")]
    return ExtractionResult(email_id="ignored", actionability=Actionability.ACTIONABLE, primary_intents=[intent], amounts=amounts, deadlines=deadlines, reasoning_summary=intent.value)


def test_purchase_threshold_and_deadline_boundaries() -> None:
    message = normalize_email(email("Purchase request"))
    at_threshold = route_email(message, extraction(Intent.DIRECT_PURCHASE, value=1_000_000, deadline_hours=72))
    assert at_threshold.task.assignee_id == AssigneeId.ROHIT
    assert at_threshold.task.priority.value == "high"
    above = route_email(message, extraction(Intent.DIRECT_PURCHASE, value=1_000_001, deadline_hours=73))
    assert above.task.assignee_id == AssigneeId.AARTI
    assert above.task.priority.value == "medium"


def test_finance_amount_never_becomes_deal_value() -> None:
    message = normalize_email(email("Invoice payment due"))
    result = ExtractionResult(
        email_id=message.email.email_id, actionability=Actionability.ACTIONABLE,
        primary_intents=[Intent.FINANCE_INVOICE],
        amounts=[AmountMention(value_inr=2_500_000, original_currency="INR", original_text="25 lakh", role="invoice_amount", evidence="invoice 25 lakh")],
        reasoning_summary="invoice",
    )
    decision = route_email(message, result)
    assert decision.task.category == Category.FINANCE
    assert decision.task.deal_value_inr is None


def test_strong_suppressions_and_weak_spam() -> None:
    ooo = normalize_email(email("I am out of office on annual leave with limited email access.", subject="Automatic reply: annual leave"))
    assert deterministic_suppression(ooo).skip_reason == SkipReason.OUT_OF_OFFICE
    weak = normalize_email(email("Could we discuss webinar promotion together?", subject="Webinar idea"))
    assert deterministic_suppression(weak) is None


def test_reply_can_explicitly_clear_fields() -> None:
    message = normalize_email(email("The budget and deadline are withdrawn.", index=1, reply=True))
    result = extraction(Intent.DIRECT_PURCHASE)
    result.reply_changes = ReplyChanges(
        deal_value=FieldChange(action="clear"), due_date=FieldChange(action="clear"),
    )
    prior = {
        "source_email_id": "original", "assignee_id": "u_aarti", "category": "enterprise_rfp",
        "priority": "high", "confidence": .9, "deal_value_inr": 2_500_000,
        "due_date": date(2026, 8, 10), "company_name": "Acme", "description": "Original request",
    }
    decision = route_email(message, result, prior_task=prior)
    assert decision.task.deal_value_inr is None
    assert decision.task.due_date is None
    assert decision.task.source_email_id == "original"


def test_reply_due_date_accepts_quoted_iso_datetime() -> None:
    message = normalize_email(email("Please use the revised deadline.", index=1, reply=True))
    result = extraction(Intent.DIRECT_PURCHASE)
    result.reply_changes = ReplyChanges(
        due_date=FieldChange(action="set", value="'2026-08-06T19:35:00+05:30'"),
    )
    prior = {
        "source_email_id": "original", "assignee_id": "u_rohit", "category": "smb_enquiry",
        "priority": "medium", "confidence": .8,
    }
    decision = route_email(message, result, prior_task=prior)
    assert decision.task.due_date == date(2026, 8, 6)


def test_orphan_reply_is_rejected() -> None:
    client = TestClient(app)
    item = email("Following up", index=1, reply=True).model_dump(mode="json")
    response = client.post("/ingest", json={"candidate_id": "mahendrushivam123@gmail.com", "emails": [item]})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "orphan_reply"


def test_acknowledgement_is_noop_on_existing_task() -> None:
    message = normalize_email(email("Thanks, received.", index=1, reply=True))
    suppressed = deterministic_suppression(message)
    assert suppressed.actionability == Actionability.NON_ACTIONABLE
    prior = {"source_email_id": "original", "assignee_id": "u_rohit", "category": "smb_enquiry", "priority": "medium", "confidence": .8}
    assert route_email(message, suppressed, prior_task=prior).operation == Operation.NOOP
