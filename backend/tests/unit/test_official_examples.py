from __future__ import annotations

from datetime import datetime

import pytest

from backend.app.domain.email_models import EmailMessage
from backend.app.domain.enums import Actionability, Operation, SkipReason
from backend.app.domain.extraction_models import (
    AmountMention,
    DeadlineMention,
    ExtractionResult,
    FieldChange,
    Intent,
    ReplyChanges,
)
from backend.app.domain.routing_policy import route_email
from backend.app.services.email_normalizer import normalize_email
from backend.app.services.suppression import deterministic_suppression


IST = "+05:30"


def message(
    number: int,
    body: str,
    *,
    subject: str,
    received_at: str = "2026-08-01T09:00:00+05:30",
    thread_id: str | None = None,
    index: int = 0,
    is_reply: bool = False,
    from_name: str = "Buyer",
    from_email: str = "buyer@example.com",
) -> EmailMessage:
    return EmailMessage(
        email_id=f"official-{number}-{index}",
        thread_id=thread_id or f"official-thread-{number}",
        message_index=index,
        from_name=from_name,
        from_email=from_email,
        to="sales@example.com",
        cc=[],
        subject=subject,
        body=body,
        received_at=received_at,
        attachments=[],
        is_reply=is_reply,
    )


def amount(value: int, role: str, evidence: str) -> AmountMention:
    return AmountMention(value_inr=value, original_currency="INR", original_text=evidence, role=role, evidence=evidence)


def deadline(value: str, role: str, evidence: str) -> DeadlineMention:
    return DeadlineMention(resolved_at=datetime.fromisoformat(value), role=role, evidence=evidence)


@pytest.mark.parametrize(
    ("number", "email", "extraction", "expected"),
    [
        (
            1,
            message(1, "Meridian Steel invites proposals for an enterprise DMS covering 4 plants and ~1,200 users. Indicative budget is Rs. 25 lakhs. Proposals must reach us by 12th August 2026.", subject="RFP - Enterprise DMS for Meridian Steel"),
            ExtractionResult(email_id="official-1-0", actionability="actionable", primary_intents=[Intent.FORMAL_RFP], intent_direction="buying_from_us", organization_name="Meridian Steel", organization_evidence="Meridian Steel", amounts=[amount(2_500_000, "deal_budget", "Rs. 25 lakhs")], deadlines=[deadline("2026-08-12T23:59:00+05:30", "submission", "12th August 2026")], reasoning_summary="Formal enterprise proposal request."),
            {"assignee_id": "u_aarti", "category": "enterprise_rfp", "priority": "medium", "due_date": "2026-08-12", "deal_value_inr": 2_500_000, "company_name": "Meridian Steel"},
        ),
        (
            2,
            message(2, "Hi, we're a 30-person logistics startup in Pune. Can we get a demo sometime next week? Nothing urgent. - Ankit Bose, Founder, Railyard Logistics", subject="Product demo", from_name="Ankit Bose", from_email="ankit@railyardlogistics.in"),
            ExtractionResult(email_id="official-2-0", actionability="actionable", primary_intents=[Intent.DEMO_REQUEST], intent_direction="buying_from_us", organization_name="Railyard Logistics", organization_evidence="Railyard Logistics", urgency="explicit_low", reasoning_summary="Small-company demo request."),
            {"assignee_id": "u_rohit", "category": "smb_enquiry", "priority": "low", "due_date": None, "deal_value_inr": None, "company_name": "Railyard Logistics"},
        ),
        (
            3,
            message(3, "Tender Notice No. BHEL/PROC/2026/0847. Bharat Heavy Electricals Limited invites bids for supply of analytics software licences. Estimated value: Rs. 6,50,000. Last date for bid submission: 03-08-2026, 1700 hrs IST.", subject="BHEL tender", received_at="2026-08-01T14:20:00+05:30", from_name="BHEL Procurement", from_email="procurement@bhel.in"),
            ExtractionResult(email_id="official-3-0", actionability="actionable", primary_intents=[Intent.TENDER], intent_direction="buying_from_us", organization_name="Bharat Heavy Electricals Limited", organization_evidence="Bharat Heavy Electricals Limited", organization_type="psu", procurement_type="tender", is_government_or_psu=True, amounts=[amount(650_000, "deal_budget", "Rs. 6,50,000")], deadlines=[deadline("2026-08-03T17:00:00+05:30", "submission", "03-08-2026, 1700")], urgency="urgent", reasoning_summary="PSU tender."),
            {"assignee_id": "u_aarti", "category": "enterprise_rfp", "priority": "high", "due_date": "2026-08-03", "deal_value_inr": 650_000, "company_name": "Bharat Heavy Electricals Limited"},
        ),
        (
            4,
            message(4, "We're finalising sponsors for the India SaaS Summit in Bengaluru. Gold tier is ₹4,00,000 and includes a keynote slot. We need confirmation by tomorrow EOD as we're going to print. - Nandita Reddy, Sponsorship Lead", subject="India SaaS Summit sponsorship", received_at="2026-08-02T16:45:00+05:30", from_name="Nandita Reddy", from_email="nandita@indiasaasummit.in"),
            ExtractionResult(email_id="official-4-0", actionability="actionable", primary_intents=[Intent.MARKETING_SPONSORSHIP], intent_direction="collaboration", organization_name="India SaaS Summit", organization_evidence="India SaaS Summit", amounts=[amount(400_000, "sponsorship_package", "₹4,00,000")], deadlines=[deadline("2026-08-03T23:59:00+05:30", "confirmation", "tomorrow EOD")], urgency="urgent", reasoning_summary="Event sponsorship request."),
            {"assignee_id": "u_meera", "category": "marketing", "priority": "high", "due_date": "2026-08-03", "deal_value_inr": 400_000, "company_name": "India SaaS Summit"},
        ),
        (
            5,
            message(5, "Please find attached invoice INV-2026-0331 for Rs. 1,18,000 (incl. 18% GST) against PO-88214. Kindly process - payment terms were Net 30 and this is now 12 days overdue. Also, our GSTIN has changed, updated details attached.", subject="Overdue invoice INV-2026-0331", from_name="Vantage Cloud Services", from_email="billing@vantagecloudservices.in"),
            ExtractionResult(email_id="official-5-0", actionability="actionable", primary_intents=[Intent.FINANCE_INVOICE, Intent.FINANCE_PAYMENT, Intent.FINANCE_GST], intent_direction="unclear", organization_name="Vantage Cloud Services", organization_evidence="sender organization", amounts=[amount(118_000, "invoice_amount", "Rs. 1,18,000")], urgency="overdue", reasoning_summary="Overdue invoice and GST correction."),
            {"assignee_id": "u_divya", "category": "finance", "priority": "high", "due_date": None, "deal_value_inr": None, "company_name": "Vantage Cloud Services"},
        ),
        (
            6,
            message(6, "We're a Salesforce implementation partner across MEA with 40+ enterprise clients. We'd like to explore reselling your platform in the region, or a technical integration at minimum. Who handles partnerships?", subject="MEA reseller partnership", from_name="Zenith Cloud Partners", from_email="alliances@zenithcloudpartners.com"),
            ExtractionResult(email_id="official-6-0", actionability="actionable", primary_intents=[Intent.RESELLER, Intent.TECHNOLOGY_INTEGRATION], intent_direction="collaboration", organization_name="Zenith Cloud Partners", organization_evidence="sender organization", alliance_subtype="reseller", reasoning_summary="Reseller and integration partnership."),
            {"assignee_id": "u_karan", "category": "alliances", "priority": "medium", "due_date": None, "deal_value_inr": None, "company_name": "Zenith Cloud Partners"},
        ),
        (
            11,
            message(11, "Hi - we met at your booth in Mumbai. Two things: (1) we'd like to evaluate your platform for our 800-person org, budget TBD but likely significant, and (2) our CMO wants to co-host a webinar with your team in September. Can you loop in the right people? - Farhan Qureshi, VP Strategy, Halcyon Retail", subject="Platform evaluation and webinar", from_name="Farhan Qureshi", from_email="farhan@halcyonretail.in"),
            ExtractionResult(email_id="official-11-0", actionability="ambiguous", primary_intents=[Intent.PRODUCT_ENQUIRY, Intent.WEBINAR_COLLABORATION], intent_direction="unclear", organization_name="Halcyon Retail", organization_evidence="Halcyon Retail", multiple_material_asks=True, reasoning_summary="Separate product evaluation and webinar asks need different owners."),
            {"assignee_id": "u_triage", "category": "triage", "priority": "medium", "due_date": None, "deal_value_inr": None, "company_name": "Halcyon Retail", "confidence": 0.42},
        ),
        (
            12,
            message(12, "Bhai, humko aapka product chahiye for our dealer network. Around 150 users honge. Budget approx 1.2 cr allocated hai for this FY. Kab connect kar sakte hain? Thoda jaldi, board review 20th ko hai.", subject="Product requirement", received_at="2026-08-05T09:00:00+05:30", from_name="Amit", from_email="amit@gmail.com"),
            ExtractionResult(email_id="official-12-0", actionability="actionable", primary_intents=[Intent.DIRECT_PURCHASE], intent_direction="buying_from_us", amounts=[amount(12_000_000, "deal_budget", "1.2 cr")], deadlines=[deadline("2026-08-20T23:59:00+05:30", "confirmation", "board review 20th")], reasoning_summary="Informal direct product purchase."),
            {"assignee_id": "u_aarti", "category": "enterprise_rfp", "priority": "medium", "due_date": "2026-08-20", "deal_value_inr": 12_000_000, "company_name": None},
        ),
    ],
    ids=lambda item: f"example-{item}" if isinstance(item, int) else None,
)
def test_official_actionable_examples(number, email, extraction, expected) -> None:
    decision = route_email(normalize_email(email), extraction)
    task = decision.task.model_dump(mode="json")
    for field, value in expected.items():
        assert task[field] == value, f"Example {number}: {field}"


@pytest.mark.parametrize(
    ("number", "email", "reason"),
    [
        (7, message(7, "I am out of office until 14th August with limited access to email. For urgent matters please contact raghav@northbridge.in.", subject="Automatic reply: Out of office", from_email="person@northbridge.in"), SkipReason.OUT_OF_OFFICE),
        (8, message(8, "Hi, I noticed your website isn't ranking on page 1 for key terms. We've helped 200+ SaaS companies 3x their organic traffic. We do content marketing, PR outreach, and webinar promotion. Free audit attached - interested in a quick 15 min call?", subject="Free SEO audit", from_email="sales@seovendor.example"), SkipReason.VENDOR_SPAM),
        (9, message(9, "The B2B Growth Weekly - Issue #212. In this edition: why PLG is stalling, 5 pricing experiments that worked, and a teardown of Figma's onboarding. [Unsubscribe]", subject="B2B Growth Weekly newsletter"), SkipReason.NEWSLETTER),
    ],
)
def test_official_suppression_examples(number, email, reason) -> None:
    extraction = deterministic_suppression(normalize_email(email))
    assert extraction is not None, f"Example {number} was not suppressed"
    assert extraction.skip_reason == reason
    assert route_email(normalize_email(email), extraction).operation == Operation.SKIP


def test_official_example_10_updates_the_original_task() -> None:
    prior = {
        "task_id": "tsk_8f2a1c",
        "candidate_id": "mahendrushivam123@gmail.com",
        "source_email_id": "official-1-0",
        "thread_id": "th_0091",
        "title": "RFP - Enterprise DMS for Meridian Steel",
        "description": "Original RFP",
        "assignee_id": "u_aarti",
        "category": "enterprise_rfp",
        "priority": "medium",
        "due_date": "2026-08-12",
        "deal_value_inr": 2_500_000,
        "company_name": "Meridian Steel",
        "confidence": 0.95,
    }
    email = message(
        10,
        "Correction to our earlier note - the board has approved an increased budget of Rs. 32 lakhs, and the submission deadline is advanced to 11th August. Apologies for the change.\n\nOn 1 Aug 2026 wrote:\nIndicative budget is Rs. 25 lakhs; deadline 12th August.",
        subject="Re: RFP - Enterprise DMS for Meridian Steel",
        received_at="2026-08-09T09:00:00+05:30",
        thread_id="th_0091",
        index=1,
        is_reply=True,
    )
    extraction = ExtractionResult(
        email_id="official-10-1",
        actionability=Actionability.ACTIONABLE,
        primary_intents=[Intent.FORMAL_RFP],
        intent_direction="buying_from_us",
        amounts=[amount(3_200_000, "deal_budget", "Rs. 32 lakhs")],
        deadlines=[deadline("2026-08-11T23:59:00+05:30", "submission", "11th August")],
        urgency="urgent",
        reply_changes=ReplyChanges(
            deal_value=FieldChange(action="set", value=3_200_000),
            due_date=FieldChange(action="set", value="2026-08-11"),
        ),
        reasoning_summary="Budget and submission deadline corrected.",
    )
    decision = route_email(normalize_email(email), extraction, prior_task=prior)
    assert decision.operation == Operation.UPDATE
    assert decision.task.source_email_id == "official-1-0"
    assert decision.task.priority.value == "high"
    assert decision.task.due_date.isoformat() == "2026-08-11"
    assert decision.task.deal_value_inr == 3_200_000


def test_model_multi_ask_noise_cannot_override_same_owner_intents() -> None:
    finance_email = message(50, "Invoice is 12 days overdue and our GSTIN changed.", subject="Overdue invoice")
    finance = ExtractionResult(
        email_id=finance_email.email_id,
        actionability="actionable",
        primary_intents=[Intent.FINANCE_INVOICE, Intent.FINANCE_GST],
        multiple_material_asks=True,
        urgency="urgent",
        reasoning_summary="Invoice and GST update.",
    )
    assert route_email(normalize_email(finance_email), finance).task.assignee_id.value == "u_divya"

    alliance_email = message(51, "We want a reseller or technical integration partnership.", subject="Partnership")
    alliance = ExtractionResult(
        email_id=alliance_email.email_id,
        actionability="actionable",
        primary_intents=[Intent.RESELLER, Intent.TECHNOLOGY_INTEGRATION],
        multiple_material_asks=True,
        reasoning_summary="Reseller or integration.",
    )
    assert route_email(normalize_email(alliance_email), alliance).task.assignee_id.value == "u_karan"


def test_board_review_date_is_actionable_but_thoda_jaldi_is_not_high() -> None:
    email = message(52, "Budget 1.2 cr. Thoda jaldi, board review 20th ko hai.", subject="Product", received_at="2026-08-05T09:00:00+05:30")
    extraction = ExtractionResult(
        email_id=email.email_id,
        actionability="actionable",
        primary_intents=[Intent.DIRECT_PURCHASE, Intent.PRODUCT_ENQUIRY],
        amounts=[amount(12_000_000, "deal_budget", "1.2 cr")],
        deadlines=[deadline("2026-08-20T00:00:00+05:30", "meeting_preference", "board review 20th ko hai")],
        urgency="urgent",
        multiple_material_asks=True,
        reasoning_summary="Purchase before board review.",
    )
    task = route_email(normalize_email(email), extraction).task
    assert task.assignee_id.value == "u_aarti"
    assert task.priority.value == "medium"
    assert task.due_date.isoformat() == "2026-08-20"


def test_pr_roundtable_invitation_is_not_treated_as_non_actionable() -> None:
    email = message(
        53,
        "CloudMint Software is hosting an informal media roundtable next month and would "
        "value your spokesperson's participation. No response deadline; this is an invitation only.",
        subject="PR roundtable invitation",
    )
    noisy_model_result = ExtractionResult(
        email_id=email.email_id,
        actionability=Actionability.NON_ACTIONABLE,
        intent_direction="unclear",
        reasoning_summary="Model incorrectly treated invitation-only wording as informational.",
    )
    task = route_email(normalize_email(email), noisy_model_result).task
    assert task is not None
    assert task.assignee_id.value == "u_meera"
    assert task.category.value == "marketing"
    assert task.priority.value == "low"
