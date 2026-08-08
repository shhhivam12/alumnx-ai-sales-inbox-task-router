from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from backend.app.domain.enums import Actionability, AssigneeId, SkipReason


class Intent(StrEnum):
    FORMAL_RFP = "formal_rfp"
    FORMAL_RFI = "formal_rfi"
    TENDER = "tender"
    DIRECT_PURCHASE = "direct_purchase"
    DEMO_REQUEST = "demo_request"
    PRODUCT_ENQUIRY = "product_enquiry"
    MARKETING_SPONSORSHIP = "marketing_sponsorship"
    WEBINAR_COLLABORATION = "webinar_collaboration"
    CONTENT_COLLABORATION = "content_collaboration"
    PR_MEDIA = "pr_media"
    RESELLER = "reseller"
    CHANNEL = "channel"
    TECHNOLOGY_INTEGRATION = "technology_integration"
    OEM_MARKETPLACE = "oem_marketplace"
    REFERRAL = "referral"
    FINANCE_INVOICE = "finance_invoice"
    FINANCE_PO = "finance_po"
    FINANCE_PAYMENT = "finance_payment"
    FINANCE_GST = "finance_gst"
    FINANCE_VENDOR_BILLING = "finance_vendor_billing"
    OTHER = "other"


class AmountMention(BaseModel):
    value_inr: int | None = Field(default=None, ge=0)
    original_currency: str | None = None
    original_text: str
    role: Literal[
        "deal_budget", "sponsorship_package", "invoice_amount", "payment_amount",
        "pipeline_value", "unrelated",
    ]
    evidence: str


class DeadlineMention(BaseModel):
    resolved_at: datetime | None = None
    role: Literal[
        "submission", "confirmation", "payment", "media_response", "meeting_preference",
        "event_date", "ooo_return", "other",
    ]
    evidence: str


class FieldChange(BaseModel):
    action: Literal["set", "clear", "unchanged"] = "unchanged"
    value: str | int | float | bool | None = None


class ReplyChanges(BaseModel):
    intent: FieldChange = Field(default_factory=FieldChange)
    owner_category: FieldChange = Field(default_factory=FieldChange)
    deal_value: FieldChange = Field(default_factory=FieldChange)
    due_date: FieldChange = Field(default_factory=FieldChange)
    company: FieldChange = Field(default_factory=FieldChange)
    description: FieldChange = Field(default_factory=FieldChange)


class ExtractionResult(BaseModel):
    email_id: str
    actionability: Actionability = Actionability.AMBIGUOUS
    skip_reason: SkipReason | None = None
    primary_intents: list[Intent] = Field(default_factory=list)
    intent_direction: Literal[
        "buying_from_us", "selling_to_us", "collaboration", "automated", "broadcast", "unclear"
    ] = "unclear"
    owner_candidates: list[AssigneeId] = Field(default_factory=list)
    organization_name: str | None = None
    organization_evidence: str | None = None
    organization_type: Literal["government", "psu", "private_company", "nonprofit", "unknown"] = "unknown"
    procurement_type: Literal["rfp", "rfi", "tender", "direct_purchase", "none"] = "none"
    is_government_or_psu: bool = False
    amounts: list[AmountMention] = Field(default_factory=list)
    deadlines: list[DeadlineMention] = Field(default_factory=list)
    urgency: Literal["explicit_low", "normal", "urgent", "overdue"] = "normal"
    multiple_material_asks: bool = False
    alliance_subtype: str | None = None
    marketing_subtype: str | None = None
    topics: list[str] = Field(default_factory=list)
    reasoning_summary: str = "Insufficient structured evidence"
    content_truncated: bool = False
    reply_changes: ReplyChanges = Field(default_factory=ReplyChanges)


class ExtractionBatch(BaseModel):
    results: list[ExtractionResult]
