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


def email(
    body: str,
    *,
    subject: str = "Request",
    index: int = 0,
    reply: bool = False,
    received: datetime = RECEIVED,
) -> EmailMessage:
    return EmailMessage(
        email_id=f"edge-{uuid4().hex}", thread_id=f"thread-{uuid4().hex}", message_index=index,
        from_name="Buyer", from_email="buyer@example.com", to="sales@example.com", cc=[],
        subject=subject, body=body, received_at=received, attachments=[], is_reply=reply,
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


def test_threshold_crossing_range_routes_triage_without_fabricated_value() -> None:
    message = normalize_email(email(
        "Delta Marine expects the project to land somewhere between 8 and 14 lakh depending on modules.",
        subject="Need quote, value range still open",
    ))
    noisy = extraction(Intent.DIRECT_PURCHASE, value=1_400_000)
    decision = route_email(message, noisy)
    assert decision.task.assignee_id == AssigneeId.TRIAGE
    assert decision.task.category == Category.TRIAGE
    assert decision.task.deal_value_inr is None


def test_deterministic_deadline_and_low_priority_phrases_override_model_omissions() -> None:
    urgent_message = normalize_email(email(
        "We need an answer within 50 hours. Leadership has not aligned internally on sponsorship or procurement.",
        subject="Urgent: connect us to the correct team",
    ))
    urgent = ExtractionResult(
        email_id=urgent_message.email.email_id,
        actionability=Actionability.ACTIONABLE,
        primary_intents=[Intent.MARKETING_SPONSORSHIP, Intent.DIRECT_PURCHASE],
        multiple_material_asks=True,
        reasoning_summary="Unresolved owners.",
    )
    urgent_task = route_email(urgent_message, urgent).task
    assert urgent_task.priority.value == "high"
    assert urgent_task.due_date == (RECEIVED + timedelta(hours=50)).date()

    routine_message = normalize_email(email(
        "Would you consider a referral agreement? No active deal is attached.",
        subject="Referral partnership",
    ))
    routine_task = route_email(routine_message, extraction(Intent.REFERRAL)).task
    assert routine_task.priority.value == "low"

    meeting_message = normalize_email(email(
        "Could we get a product demo next week? It is only a meeting preference and nothing is urgent.",
        subject="Product demo next week",
    ))
    meeting_task = route_email(meeting_message, extraction(Intent.DEMO_REQUEST)).task
    assert meeting_task.priority.value == "low"
    assert meeting_task.due_date is None


def test_explicit_ist_delivery_time_overrides_model_timezone_error() -> None:
    ist = timezone(timedelta(hours=5, minutes=30))
    received = datetime(2026, 8, 1, 15, 18, tzinfo=ist)
    message = normalize_email(email(
        "Please send it before 04 Aug 2026 14:18 IST for our approval meeting.",
        subject="Quote needed before internal approval",
        received=received,
    ))
    noisy = ExtractionResult(
        email_id=message.email.email_id,
        actionability=Actionability.ACTIONABLE,
        primary_intents=[Intent.DIRECT_PURCHASE],
        amounts=[AmountMention(
            value_inr=200_000,
            original_currency="INR",
            original_text="Rs 2 lakh",
            role="deal_budget",
            evidence="Rs 2 lakh",
        )],
        deadlines=[DeadlineMention(
            resolved_at=datetime(2026, 8, 4, 14, 18, tzinfo=timezone.utc),
            role="meeting_preference",
            evidence="04 Aug 2026 14:18 IST",
        )],
        reasoning_summary="Model used UTC for an explicit IST deadline.",
    )
    task = route_email(message, noisy).task
    assert task.priority.value == "high"
    assert task.due_date.isoformat() == "2026-08-04"


def test_award_nomination_rescues_incorrect_model_skip_reason() -> None:
    message = normalize_email(email(
        "We would like to nominate your company for our SaaS awards. Please approve the profile by 07 Aug 2026 14:43 IST.",
        subject="Award nomination closes soon",
    ))
    noisy = ExtractionResult(
        email_id=message.email.email_id,
        actionability=Actionability.NON_ACTIONABLE,
        skip_reason=SkipReason.NEWSLETTER,
        reasoning_summary="Model incorrectly treated the direct nomination as broadcast content.",
    )
    decision = route_email(message, noisy)
    assert decision.operation == Operation.CREATE
    assert decision.task.assignee_id == AssigneeId.MEERA
    assert decision.task.category == Category.MARKETING


def test_hinglish_product_budget_cannot_be_misread_as_dealer_alliance() -> None:
    message = normalize_email(email(
        "Bhai, humko aapka product chahiye for our dealer network. Budget approx 1.2 cr allocated hai.",
        subject="Dealer network ke liye product chahiye",
    ))
    noisy = ExtractionResult(
        email_id=message.email.email_id,
        actionability=Actionability.ACTIONABLE,
        primary_intents=[Intent.RESELLER],
        amounts=[AmountMention(
            value_inr=12_000_000,
            original_currency="INR",
            original_text="1.2 cr",
            role="deal_budget",
            evidence="1.2 cr",
        )],
        reasoning_summary="Model confused dealer network with reseller intent.",
    )
    task = route_email(message, noisy).task
    assert task.assignee_id == AssigneeId.AARTI
    assert task.category == Category.ENTERPRISE_RFP


def test_field_only_reply_preserves_owner_even_when_model_repeats_wrong_intent() -> None:
    message = normalize_email(email(
        "Please correct the customer name in your record to Delta Marine Private Limited.",
        subject="Re: Quote needed",
        index=1,
        reply=True,
    ))
    noisy = ExtractionResult(
        email_id=message.email.email_id,
        actionability=Actionability.ACTIONABLE,
        primary_intents=[Intent.FORMAL_RFP],
        reply_changes=ReplyChanges(company=FieldChange(action="set", value="Delta Marine Private Limited")),
        organization_name="Delta Marine Private Limited",
        reasoning_summary="Company correction only.",
    )
    prior = {
        "source_email_id": "original",
        "assignee_id": "u_rohit",
        "category": "smb_enquiry",
        "priority": "low",
        "confidence": 0.9,
        "deal_value_inr": 200_000,
        "company_name": "Delta Marine",
        "description": "Original quote",
    }
    task = route_email(message, noisy, prior_task=prior).task
    assert task.assignee_id == AssigneeId.ROHIT
    assert task.category == Category.SMB_ENQUIRY
    assert task.company_name == "Delta Marine Private Limited"


def test_unconfirmed_public_sector_opportunity_remains_triage() -> None:
    message = normalize_email(email(
        "We advise an unnamed public entity, but this is not yet an official tender. "
        "We may either prime the bid or purchase licences.",
        subject="Confidential public-sector opportunity",
    ))
    noisy = extraction(Intent.RESELLER)
    task = route_email(message, noisy).task
    assert task.assignee_id == AssigneeId.TRIAGE
    assert task.category == Category.TRIAGE


def test_explicit_inr_amounts_are_recovered_when_model_omits_them() -> None:
    rfp_message = normalize_email(email(
        "Meridian Steel invites proposals. Indicative budget is Rs. 25 lakhs.",
        subject="Enterprise RFP",
    ))
    rfp = ExtractionResult(
        email_id=rfp_message.email.email_id,
        actionability=Actionability.ACTIONABLE,
        primary_intents=[Intent.FORMAL_RFP],
        reasoning_summary="Model omitted amount.",
    )
    assert route_email(rfp_message, rfp).task.deal_value_inr == 2_500_000

    tender_message = normalize_email(email(
        "Government PSU tender. Estimated value: Rs. 6,50,000.",
        subject="Tender",
    ))
    tender = ExtractionResult(
        email_id=tender_message.email.email_id,
        actionability=Actionability.ACTIONABLE,
        primary_intents=[Intent.TENDER],
        is_government_or_psu=True,
        reasoning_summary="Model omitted amount.",
    )
    assert route_email(tender_message, tender).task.deal_value_inr == 650_000

    crore_message = normalize_email(email(
        "Bhai, humko aapka product chahiye. Budget approx 1.2 cr allocated hai.",
        subject="Product requirement",
    ))
    crore = ExtractionResult(
        email_id=crore_message.email.email_id,
        actionability=Actionability.ACTIONABLE,
        primary_intents=[Intent.RESELLER],
        reasoning_summary="Model omitted amount and confused intent.",
    )
    crore_task = route_email(crore_message, crore).task
    assert crore_task.deal_value_inr == 12_000_000
    assert crore_task.assignee_id == AssigneeId.AARTI


def test_model_currency_punctuation_and_omitted_hinglish_board_deadline() -> None:
    item = normalize_email(email(
        "Budget approx 1.2 cr allocated hai. Thoda jaldi, board review 20th ko hai.",
        subject="Product requirement",
    ))
    extracted = ExtractionResult(
        email_id=item.email.email_id,
        actionability=Actionability.ACTIONABLE,
        primary_intents=[Intent.DIRECT_PURCHASE],
        intent_direction="buying_from_us",
        amounts=[AmountMention(
            value_inr=12_000_000,
            original_currency="Rs.",
            original_text="1.2 cr",
            role="deal_budget",
            evidence="1.2 cr",
        )],
        reasoning_summary="Model returned the value but omitted the board-review deadline.",
    )
    task = route_email(item, extracted).task
    assert task.deal_value_inr == 12_000_000
    assert task.due_date.isoformat() == "2026-08-20"


def test_invoice_and_alliance_pipeline_amounts_are_not_deal_values_when_recovered() -> None:
    finance_message = normalize_email(email(
        "Invoice INV-1 for INR 1,18,000 is overdue.",
        subject="Invoice",
    ))
    finance = ExtractionResult(
        email_id=finance_message.email.email_id,
        actionability=Actionability.ACTIONABLE,
        primary_intents=[Intent.FINANCE_INVOICE],
        reasoning_summary="Invoice.",
    )
    assert route_email(finance_message, finance).task.deal_value_inr is None

    alliance_message = normalize_email(email(
        "Referral partnership with a downstream pipeline of 25 lakh.",
        subject="Partnership",
    ))
    alliance = ExtractionResult(
        email_id=alliance_message.email.email_id,
        actionability=Actionability.ACTIONABLE,
        primary_intents=[Intent.REFERRAL],
        reasoning_summary="Alliance.",
    )
    assert route_email(alliance_message, alliance).task.deal_value_inr is None
