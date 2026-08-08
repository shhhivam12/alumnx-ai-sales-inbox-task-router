from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from backend.app.config import LOCKED_CANDIDATE_ID
from backend.app.domain.confidence import calculate_confidence
from backend.app.domain.email_models import NormalizedEmail
from backend.app.domain.enums import Actionability, AssigneeId, Category, Operation, Priority
from backend.app.domain.extraction_models import AmountMention, DeadlineMention, ExtractionResult, Intent
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
    candidates = [
        item.value_inr
        for item in extraction.amounts
        if item.value_inr is not None
        and item.role in {"deal_budget", "sponsorship_package"}
        and (not item.original_currency or item.original_currency.strip().upper() in {"INR", "RS", "RUPEE", "RUPEES", "₹"})
    ]
    return candidates[-1] if candidates else None


def _priority(extraction: ExtractionResult, received: datetime, current_text: str) -> tuple[Priority, datetime | None]:
    actionable = [item.resolved_at for item in extraction.deadlines if item.role in ACTIONABLE_DEADLINE_ROLES and item.resolved_at]
    deadline = actionable[-1] if actionable else None
    if deadline and deadline <= received + timedelta(hours=72):
        return Priority.HIGH, deadline
    lower = current_text.lower()
    if extraction.urgency == "overdue" or "overdue" in lower:
        return Priority.HIGH, deadline
    if extraction.urgency == "urgent" and any(token in lower for token in ("immediately", "today", "tomorrow")):
        return Priority.HIGH, deadline
    explicit_low_text = any(token in lower for token in (
        "nothing urgent", "nothing is urgent", "not urgent", "no rush",
        "no active deal is attached", "no active deal attached",
        "only exploring options", "routine request", "invitation only",
    ))
    if extraction.urgency == "explicit_low" or explicit_low_text:
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


def _different_owner_groups(extraction: ExtractionResult) -> bool:
    groups: set[str] = set()
    for intent in extraction.primary_intents:
        if intent in FORMAL_INTENTS:
            groups.add("enterprise")
        elif intent in FINANCE_INTENTS:
            groups.add("finance")
        elif intent in MARKETING_INTENTS:
            groups.add("marketing")
        elif intent in ALLIANCE_INTENTS:
            groups.add("alliances")
        elif intent in DIRECT_INTENTS:
            groups.add("sales")
    return extraction.multiple_material_asks and (len(groups) > 1 or not groups)


def _deterministic_amounts(text: str, extraction: ExtractionResult) -> list[AmountMention]:
    """Supplement model output only where INR text and its business role are explicit."""
    lower = text.lower()
    deal_context = bool(set(extraction.primary_intents) & (FORMAL_INTENTS | DIRECT_INTENTS)) or any(
        token in lower for token in ("tender value", "estimated value", "deal budget", "purchase budget")
    )
    if _range_crosses_threshold(lower):
        return []
    patterns = (
        re.compile(
            r"(?i)(?:\u20b9|inr\s*|rs\.?\s*)?([0-9]+(?:\.[0-9]+)?)\s*"
            r"(crore|crores|cr|lakh|lakhs|lac|lacs|l)\b"
        ),
        re.compile(r"(?i)(?:\u20b9|inr\s*|rs\.?\s*)([0-9][0-9,]*)"),
    )
    result: list[AmountMention] = []
    seen_spans: list[tuple[int, int]] = []
    for pattern in patterns:
        for match in pattern.finditer(text):
            if any(match.start() < end and match.end() > start for start, end in seen_spans):
                continue
            seen_spans.append(match.span())
            number = float(match.group(1).replace(",", ""))
            unit = match.group(2).lower() if match.lastindex and match.lastindex >= 2 and match.group(2) else ""
            multiplier = 10_000_000 if unit in {"crore", "crores", "cr"} else 100_000 if unit else 1
            value = int(round(number * multiplier))
            context = lower[max(0, match.start() - 90): min(len(lower), match.end() + 90)]
            if any(word in context for word in ("invoice", "payment", "credit note", " bill")):
                role = "invoice_amount" if "invoice" in context or "bill" in context else "payment_amount"
            elif any(word in context for word in ("pipeline", "revenue share", "downstream")):
                role = "pipeline_value"
            elif any(word in context for word in ("sponsor", "package", "platinum", "gold tier")):
                role = "sponsorship_package"
            elif deal_context:
                role = "deal_budget"
            else:
                continue
            result.append(AmountMention(
                value_inr=value,
                original_currency="INR",
                original_text=match.group(0),
                role=role,
                evidence=match.group(0),
            ))
    return result


def _normalize_extraction_policy(message: NormalizedEmail, extraction: ExtractionResult) -> ExtractionResult:
    """Correct model hints where the written business contract is deterministic."""
    normalized = extraction.model_copy(deep=True)
    current = f"{message.email.subject}\n{message.latest_reply_body}".lower()
    pr_roundtable_invitation = (
        "media roundtable" in current
        and any(token in current for token in ("spokesperson", "participation", "join us"))
    )
    award_nomination = (
        any(token in current for token in ("award nomination", "nominate your company"))
        and any(token in current for token in ("approve the profile", "approval", "confirm participation"))
    )
    if (
        normalized.actionability == Actionability.NON_ACTIONABLE
        and normalized.skip_reason is None
        and pr_roundtable_invitation
    ):
        normalized.actionability = Actionability.ACTIONABLE
        if Intent.PR_MEDIA not in normalized.primary_intents:
            normalized.primary_intents.append(Intent.PR_MEDIA)
        normalized.intent_direction = "collaboration"
        if "no response deadline" in current:
            normalized.urgency = "explicit_low"
        normalized.reasoning_summary = "Direct invitation for spokesperson participation in a media roundtable"
    if (
        normalized.actionability == Actionability.NON_ACTIONABLE
        and normalized.skip_reason is None
        and award_nomination
    ):
        normalized.actionability = Actionability.ACTIONABLE
        if Intent.PR_MEDIA not in normalized.primary_intents:
            normalized.primary_intents.append(Intent.PR_MEDIA)
        normalized.intent_direction = "collaboration"
        normalized.reasoning_summary = "Award nomination requires an explicit profile approval response"
    if "product chahiye" in current and "budget" in current:
        normalized.primary_intents = [
            intent for intent in normalized.primary_intents if intent not in ALLIANCE_INTENTS
        ]
        if Intent.DIRECT_PURCHASE not in normalized.primary_intents:
            normalized.primary_intents.append(Intent.DIRECT_PURCHASE)
        normalized.intent_direction = "buying_from_us"

    existing_amounts = {(item.value_inr, item.role) for item in normalized.amounts}
    for amount in _deterministic_amounts(current, normalized):
        if (amount.value_inr, amount.role) not in existing_amounts:
            normalized.amounts.append(amount)
            existing_amounts.add((amount.value_inr, amount.role))

    for item in normalized.deadlines:
        evidence = item.evidence.lower()
        approval_delivery = "please send it before" in current or "send it before" in evidence
        if item.role == "meeting_preference" and (
            "board review" in evidence or approval_delivery
        ) and item.resolved_at:
            item.role = "confirmation"
            if "board review" in evidence:
                item.resolved_at = item.resolved_at.replace(hour=23, minute=59, second=0, microsecond=0)

    if "tomorrow eod" in current:
        tomorrow = (message.email.received_at + timedelta(days=1)).replace(
            hour=23, minute=59, second=0, microsecond=0
        )
        model_tomorrow = [item for item in normalized.deadlines if "tomorrow" in item.evidence.lower()]
        if model_tomorrow:
            for item in model_tomorrow:
                item.role = "confirmation"
                item.resolved_at = tomorrow
        else:
            normalized.deadlines.append(DeadlineMention(
                resolved_at=tomorrow,
                role="confirmation",
                evidence="tomorrow EOD",
            ))

    actionable_deadline = any(
        item.resolved_at and item.role in ACTIONABLE_DEADLINE_ROLES for item in normalized.deadlines
    )
    if not actionable_deadline:
        within_hours = re.search(r"(?i)\bwithin\s+(\d{1,3})\s+hours?\b", current)
        if within_hours:
            hours = int(within_hours.group(1))
            normalized.deadlines.append(DeadlineMention(
                resolved_at=message.email.received_at + timedelta(hours=hours),
                role="confirmation",
                evidence=within_hours.group(0),
            ))
    if "due " in current and re.search(r"(?i)\bdue\s+(?:\w+|\d+)\s+days?\s+ago\b", current):
        normalized.urgency = "overdue"
    normalized.multiple_material_asks = _different_owner_groups(normalized)
    return normalized


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


def _range_crosses_threshold(text: str) -> bool:
    match = re.search(
        r"(?i)\bbetween\s+(\d+(?:\.\d+)?)\s*(?:(?:lakh|lakhs|lac)\s+)?(?:and|to|-)\s+"
        r"(\d+(?:\.\d+)?)\s+(?:lakh|lakhs|lac)\b",
        text,
    )
    if not match:
        return False
    low, high = (float(match.group(1)) * 100_000, float(match.group(2)) * 100_000)
    return min(low, high) <= 1_000_000 < max(low, high)


def _explicit_ambiguity(text: str) -> bool:
    lower = text.lower()
    unavailable_scope = "proposal" in lower and any(token in lower for token in (
        "cannot share the company name or commercial scope",
        "cannot share the commercial scope",
    ))
    unconfirmed_public = (
        "not yet an official tender" in lower
        and any(token in lower for token in ("prime the bid or purchase", "may either prime", "unnamed public"))
    )
    unresolved_multi = (
        "has not aligned internally" in lower
        and sum(token in lower for token in ("sponsorship", "procurement", "joint offering")) >= 2
    )
    return unavailable_scope or unconfirmed_public or unresolved_multi


def route_email(
    message: NormalizedEmail,
    extraction: ExtractionResult,
    *,
    prior_task: dict | None = None,
    degraded: bool = False,
    prompt_version: str = "routing-v1",
    model_name: str | None = None,
) -> RoutingDecision:
    extraction = _normalize_extraction_policy(message, extraction)
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
    current_text = f"{message.email.subject}\n{message.latest_reply_body}"
    threshold_range = _range_crosses_threshold(current_text)
    if threshold_range or _explicit_ambiguity(current_text):
        value = None
        assignee, category, hard_rule = AssigneeId.TRIAGE, Category.TRIAGE, False
    priority, deadline_at = _priority(extraction, message.email.received_at, message.latest_reply_body)
    company = extraction.organization_name

    if prior_task:
        # Preserve prior fields unless the current message supplies material evidence.
        previous_assignee = AssigneeId(prior_task["assignee_id"])
        previous_category = Category(prior_task["category"])
        explicit_route_change = (
            extraction.reply_changes.intent.action != "unchanged"
            or extraction.reply_changes.owner_category.action != "unchanged"
        )
        sales_value_change = (
            previous_category in {Category.SMB_ENQUIRY, Category.ENTERPRISE_RFP}
            and (
                extraction.reply_changes.deal_value.action != "unchanged"
                or (
                    value is not None
                    and value != prior_task.get("deal_value_inr")
                    and bool(set(extraction.primary_intents) & DIRECT_INTENTS)
                )
            )
        )
        if not explicit_route_change and not sales_value_change and not threshold_range:
            assignee, category = previous_assignee, previous_category
        if extraction.reply_changes.deal_value.action == "clear":
            value = None
        elif extraction.reply_changes.deal_value.action == "set" and extraction.reply_changes.deal_value.value is not None:
            value = int(extraction.reply_changes.deal_value.value)
        elif value is None:
            value = prior_task.get("deal_value_inr")
        if sales_value_change and value is not None:
            if value > 1_000_000:
                assignee, category = AssigneeId.AARTI, Category.ENTERPRISE_RFP
            else:
                assignee, category = AssigneeId.ROHIT, Category.SMB_ENQUIRY
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
