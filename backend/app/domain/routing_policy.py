from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from backend.app.config import LOCKED_CANDIDATE_ID
from backend.app.domain.confidence import calculate_confidence
from backend.app.domain.email_models import NormalizedEmail
from backend.app.domain.enums import Actionability, AssigneeId, Category, Operation, Priority
from backend.app.domain.extraction_models import ExtractionResult, Intent
from backend.app.domain.task_models import RoutingDecision, TaskPayload


FINANCE_INTENTS = {
    Intent.FINANCE_INVOICE, Intent.FINANCE_PO, Intent.FINANCE_PAYMENT,
    Intent.FINANCE_GST, Intent.FINANCE_VENDOR_BILLING,
}
MARKETING_INTENTS = {
    Intent.MARKETING_SPONSORSHIP, Intent.WEBINAR_COLLABORATION,
    Intent.CONTENT_COLLABORATION, Intent.PR_MEDIA,
}
ALLIANCE_INTENTS = {
    Intent.RESELLER, Intent.CHANNEL, Intent.TECHNOLOGY_INTEGRATION,
    Intent.OEM_MARKETPLACE, Intent.REFERRAL,
}
FORMAL_INTENTS = {Intent.FORMAL_RFP, Intent.FORMAL_RFI, Intent.TENDER}
DIRECT_INTENTS = {Intent.DIRECT_PURCHASE, Intent.DEMO_REQUEST, Intent.PRODUCT_ENQUIRY}
ACTIONABLE_DEADLINE_ROLES = {"submission", "confirmation", "payment", "media_response"}


def _select_value(extraction: ExtractionResult) -> int | None:
    candidates = [item.value_inr for item in extraction.amounts if item.value_inr is not None and item.role in {"deal_budget", "sponsorship_package"}]
    return candidates[-1] if candidates else None


def _priority(extraction: ExtractionResult, received: datetime) -> tuple[Priority, datetime | None]:
    actionable = [item.resolved_at for item in extraction.deadlines if item.role in ACTIONABLE_DEADLINE_ROLES and item.resolved_at]
    deadline = actionable[-1] if actionable else None
    if deadline and deadline <= received + timedelta(hours=72):
        return Priority.HIGH, deadline
    if extraction.urgency in {"urgent", "overdue"}:
        return Priority.HIGH, deadline
    if extraction.urgency == "explicit_low":
        return Priority.LOW, deadline
    return Priority.MEDIUM, deadline


def _owner(extraction: ExtractionResult, value: int | None) -> tuple[AssigneeId, Category, bool]:
    intents = set(extraction.primary_intents)
    if extraction.multiple_material_asks:
        return AssigneeId.TRIAGE, Category.TRIAGE, False
    if extraction.is_government_or_psu and Intent.TENDER in intents:
        return AssigneeId.AARTI, Category.ENTERPRISE_RFP, True
    if intents & FORMAL_INTENTS:
        return AssigneeId.AARTI, Category.ENTERPRISE_RFP, True
    if intents & FINANCE_INTENTS:
        return AssigneeId.DIVYA, Category.FINANCE, True
    if intents & MARKETING_INTENTS:
        return AssigneeId.MEERA, Category.MARKETING, False
    if intents & ALLIANCE_INTENTS:
        return AssigneeId.KARAN, Category.ALLIANCES, False
    if intents & DIRECT_INTENTS:
        if value is not None:
            return (AssigneeId.AARTI, Category.ENTERPRISE_RFP, False) if value > 1_000_000 else (AssigneeId.ROHIT, Category.SMB_ENQUIRY, False)
        if Intent.DEMO_REQUEST in intents or Intent.PRODUCT_ENQUIRY in intents:
            return AssigneeId.ROHIT, Category.SMB_ENQUIRY, False
    return AssigneeId.TRIAGE, Category.TRIAGE, False


def _title(message: NormalizedEmail, category: Category, company: str | None) -> str:
    subject = re.sub(r"(?i)^(re|fwd):\s*", "", message.email.subject).strip()
    return (subject or f"{category.value.replace('_', ' ').title()} - {company or 'Unknown company'}")[:200]


def _coerce_due_date(value: object) -> date:
    """Accept date/datetime values without trusting model-added quote characters."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip().strip("'\"")
    try:
        return date.fromisoformat(text)
    except ValueError:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()


def route_email(
    message: NormalizedEmail,
    extraction: ExtractionResult,
    *,
    prior_task: dict | None = None,
    degraded: bool = False,
    prompt_version: str = "routing-v1",
    model_name: str | None = None,
) -> RoutingDecision:
    operation = Operation.UPDATE if prior_task else Operation.CREATE
    if extraction.actionability == Actionability.NON_ACTIONABLE:
        operation = Operation.NOOP if prior_task and extraction.skip_reason is None else Operation.SKIP
        return RoutingDecision(
            email_id=message.email.email_id,
            thread_id=message.email.thread_id,
            operation=operation,
            actionability=Actionability.NON_ACTIONABLE,
            skip_reason=extraction.skip_reason,
            confidence=calculate_confidence(extraction, None, degraded=degraded),
            reasoning=extraction.reasoning_summary,
            evidence=[item for item in extraction.topics[:4]],
            primary_intents=[item.value for item in extraction.primary_intents],
            topics=extraction.topics,
            intent_direction=extraction.intent_direction,
            organization_type=extraction.organization_type,
            degraded_mode=degraded,
            model_name=model_name,
            prompt_version=prompt_version,
        )

    value = _select_value(extraction)
    assignee, category, hard_rule = _owner(extraction, value)
    priority, deadline_at = _priority(extraction, message.email.received_at)
    company = extraction.organization_name

    if prior_task:
        # Preserve prior fields unless the current message supplies material evidence.
        previous_assignee = AssigneeId(prior_task["assignee_id"])
        previous_category = Category(prior_task["category"])
        if not extraction.primary_intents:
            assignee, category = previous_assignee, previous_category
        if extraction.reply_changes.deal_value.action == "clear":
            value = None
        elif extraction.reply_changes.deal_value.action == "set" and extraction.reply_changes.deal_value.value is not None:
            value = int(extraction.reply_changes.deal_value.value)
        elif value is None:
            value = prior_task.get("deal_value_inr")
        if extraction.reply_changes.company.action == "clear":
            company = None
        elif extraction.reply_changes.company.action == "set" and extraction.reply_changes.company.value:
            company = str(extraction.reply_changes.company.value)
        elif company is None:
            company = prior_task.get("company_name")
        if extraction.reply_changes.due_date.action == "clear":
            due_date = None
        elif extraction.reply_changes.due_date.action == "set" and extraction.reply_changes.due_date.value:
            due_date = _coerce_due_date(extraction.reply_changes.due_date.value)
        elif deadline_at is None:
            previous_due = prior_task.get("due_date")
            due_date = previous_due
            priority = Priority(prior_task.get("priority", Priority.MEDIUM))
        else:
            due_date = deadline_at.date()
    else:
        due_date = deadline_at.date() if deadline_at else None

    confidence = calculate_confidence(extraction, assignee, hard_rule=hard_rule, degraded=degraded)
    if prior_task and not extraction.primary_intents:
        confidence = max(confidence, float(prior_task.get("confidence", 0.5)))
    reasoning = extraction.reasoning_summary
    if assignee == AssigneeId.TRIAGE:
        reasoning = f"Actionable ambiguity requires human review: {reasoning}"
    previous_description = str(prior_task.get("description") or "").strip() if prior_task else ""
    if extraction.reply_changes.description.action == "clear":
        description = reasoning[:2000]
    elif previous_description and reasoning.lower() not in previous_description.lower():
        description = f"{previous_description}\nUpdate: {reasoning}"[:2000]
    else:
        description = (previous_description or reasoning)[:2000]
    task = TaskPayload(
        candidate_id=LOCKED_CANDIDATE_ID,
        source_email_id=prior_task.get("source_email_id", message.email.email_id) if prior_task else message.email.email_id,
        thread_id=message.email.thread_id,
        title=_title(message, category, company),
        description=description,
        assignee_id=assignee,
        category=category,
        priority=priority,
        due_date=due_date,
        deal_value_inr=value,
        company_name=company,
        confidence=confidence,
    )
    evidence = [item.evidence for item in extraction.amounts] + [item.evidence for item in extraction.deadlines]
    if extraction.organization_evidence:
        evidence.append(extraction.organization_evidence)
    return RoutingDecision(
        email_id=message.email.email_id,
        thread_id=message.email.thread_id,
        operation=operation,
        actionability=Actionability.AMBIGUOUS if assignee == AssigneeId.TRIAGE else Actionability.ACTIONABLE,
        task=task,
        priority=priority,
        deadline_at=deadline_at,
        confidence=confidence,
        reasoning=reasoning,
        evidence=evidence[:8],
        primary_intents=[item.value for item in extraction.primary_intents],
        topics=extraction.topics,
        intent_direction=extraction.intent_direction,
        organization_type=extraction.organization_type,
        alliance_subtype=extraction.alliance_subtype,
        marketing_subtype=extraction.marketing_subtype,
        amount_mentions=[item.model_dump(mode="json") for item in extraction.amounts],
        deadline_mentions=[item.model_dump(mode="json") for item in extraction.deadlines],
        degraded_mode=degraded,
        model_name=model_name,
        prompt_version=prompt_version,
    )
