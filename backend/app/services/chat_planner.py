from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from backend.app.domain.chat_models import AnalyticsFilter, AnalyticsQuery, ChatPlan


def _normalize(question: str) -> str:
    """Normalize punctuation without changing the meaning-bearing words."""
    normalized = unicodedata.normalize("NFKC", question).lower()
    normalized = normalized.replace("’", "'").replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", normalized).strip()


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _requests_action(text: str) -> bool:
    patterns = (
        r"\b(?:send|forward|write|draft)\s+(?:an?\s+)?(?:email|mail|message)\b",
        r"\bsend\b.{0,80}\b(?:email|mail|message)\b",
        r"\b(?:email|notify|contact|message)\s+(?:aarti|rohit|meera|karan|divya|them|the\s+buyer|the\s+prospect)\b",
        r"\b(?:delete|create|assign|reassign)\s+(?:a\s+|the\s+)?task\b",
        r"\b(?:delete|create|assign|reassign|edit|close)\b.{0,60}\btasks?\b",
    )
    return any(re.search(pattern, text) for pattern in patterns)


ASSIGNEE_ALIASES = {
    "aarti": "u_aarti", "rohit": "u_rohit", "meera": "u_meera",
    "karan": "u_karan", "divya": "u_divya", "triage queue": "u_triage",
}
CATEGORY_ALIASES = {
    "enterprise_rfp": ("enterprise rfp", "enterprise rfps", "rfp", "rfps", "proposal", "proposals", "tender", "tenders"),
    "smb_enquiry": ("smb", "small business", "demo request", "demo requests", "product enquiry", "product enquiries"),
    "marketing": ("marketing", "sponsorship", "sponsorships", "webinar", "webinars"),
    "alliances": ("alliance", "alliances", "partnership", "partnerships"),
    "finance": ("finance", "invoice", "invoices", "payment", "payments", "billing"),
    "triage": ("triage", "manual review"),
}


def _general_analytics_plan(q: str) -> ChatPlan | None:
    """Build common analytics plans without requiring a model call.

    This deliberately handles only unambiguous language. The optional Gemini
    planner handles less predictable phrasing using the same validated schema.
    """
    filters: list[AnalyticsFilter] = []
    recognized = False
    metric = None

    dataset = "decisions"
    if _has_any(q, ("task", "tasks", "assigned", "assignee", "owner", "owned by")):
        dataset = "current_tasks"
        recognized = True
    if _has_any(q, ("thread", "threads", "conversation", "conversations")):
        dataset = "threads"
        recognized = True
    if _has_any(q, ("event", "events", "task update", "task updates")):
        dataset = "events"
        recognized = True
    if _has_any(q, ("feedback", "flagged as spurious", "spurious flag")):
        dataset = "feedback"
        recognized = True
    if _has_any(q, ("ingest run", "ingestion run", "runs", "run status")):
        dataset = "runs"
        recognized = True

    for alias, assignee_id in ASSIGNEE_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", q):
            filters.append(AnalyticsFilter(field="assignee_id", value=assignee_id))
            dataset = "current_tasks"
            recognized = True
            break

    for category, aliases in CATEGORY_ALIASES.items():
        if _has_any(q, aliases):
            filters.append(AnalyticsFilter(field="category", value=category))
            recognized = True
            break

    for priority in ("high", "medium", "low"):
        if _has_any(q, (f"{priority} priority", f"{priority}-priority")):
            filters.append(AnalyticsFilter(field="priority", value=priority))
            recognized = True
            break
    else:
        if re.search(r"\burgent\b", q):
            filters.append(AnalyticsFilter(field="priority", value="high"))
            recognized = True

    if _has_any(q, ("low confidence", "low-confidence", "poor confidence", "low certainty", "uncertain")):
        filters.append(AnalyticsFilter(field="confidence", operator="lte", value=0.54))
        recognized = True
    elif _has_any(q, ("high confidence", "high-confidence", "strong confidence", "high certainty")):
        filters.append(AnalyticsFilter(field="confidence", operator="gte", value=0.8))
        recognized = True

    for operation in ("create", "update", "skip", "noop"):
        if re.search(rf"\b{operation}(?:d|ped|s)?\b", q):
            filters.append(AnalyticsFilter(field="operation", value=operation))
            dataset = "decisions"
            recognized = True
            break

    skip_aliases = {
        "out_of_office": ("out of office", "ooo"),
        "newsletter": ("newsletter", "newsletters"),
        "vendor_spam": ("vendor spam", "seo pitch", "seo pitches"),
        "automated_bounce": ("automated bounce", "delivery failure", "bounced"),
    }
    for reason, aliases in skip_aliases.items():
        if _has_any(q, aliases):
            filters.append(AnalyticsFilter(field="skip_reason", value=reason))
            dataset = "decisions"
            recognized = True
            break

    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    if _has_any(q, ("due tomorrow", "due by tomorrow")):
        filters.append(AnalyticsFilter(field="due_date", value=(today + timedelta(days=1)).isoformat()))
        dataset = "current_tasks"
        recognized = True
    elif "due today" in q:
        filters.append(AnalyticsFilter(field="due_date", value=today.isoformat()))
        dataset = "current_tasks"
        recognized = True
    elif "overdue" in q:
        filters.append(AnalyticsFilter(field="due_date", operator="lt", value=today.isoformat()))
        dataset = "current_tasks"
        recognized = True

    if _has_any(q, ("without a due date", "without due date", "no due date", "missing due date")):
        filters.append(AnalyticsFilter(field="due_date", operator="is_null"))
        dataset = "current_tasks"
        recognized = True
    if _has_any(q, ("without a deal value", "without deal value", "no deal value", "missing deal value")):
        filters.append(AnalyticsFilter(field="deal_value_inr", operator="is_null"))
        dataset = "current_tasks"
        recognized = True
    if _has_any(q, ("degraded mode", "degraded")):
        filters.append(AnalyticsFilter(field="degraded_mode", value=True))
        dataset = "decisions"
        recognized = True

    group_aliases = {
        "assignee_id": ("by owner", "by assignee", "per owner", "per assignee", "each person", "each owner"),
        "category": ("by category", "per category", "each category"),
        "priority": ("by priority", "per priority", "each priority"),
        "operation": ("by operation", "per operation", "each operation"),
        "skip_reason": ("by skip reason", "per skip reason", "each skip reason"),
        "company_name": ("by company", "per company", "each company"),
        "status": ("by status", "per status", "each status"),
    }
    group_by = None
    for field, aliases in group_aliases.items():
        if _has_any(q, aliases):
            group_by = field
            recognized = True
            if field in {"operation", "skip_reason"}:
                dataset = "decisions"
            break

    count_terms = ("how many", "count", "number of", "total tasks", "total emails", "were there", "are there", "any")
    list_terms = ("list", "show", "which", "what are", "give me")
    if group_by:
        operation_name = "group_count"
    elif _has_any(q, ("average confidence", "mean confidence")):
        operation_name, metric = "average", "confidence"
        recognized = True
    elif _has_any(q, ("total deal value", "sum of deal", "combined deal value", "add up")):
        operation_name, metric = "sum", "deal_value_inr"
        dataset = "current_tasks"
        recognized = True
    elif _has_any(q, count_terms):
        operation_name = "count"
        recognized = True
    elif _has_any(q, list_terms):
        operation_name = "list"
        recognized = True
    else:
        operation_name = "list"

    if not recognized:
        return None

    default_fields = {
        "current_tasks": ["task_id", "thread_id", "title", "assignee_id", "category", "priority", "confidence", "due_date", "deal_value_inr", "company_name"],
        "decisions": ["email_id", "thread_id", "title", "operation", "skip_reason", "assignee_id", "category", "priority", "confidence", "reasoning"],
        "threads": ["thread_id", "task_id", "assignee_id", "category", "message_count", "update_count"],
        "events": ["thread_id", "email_id", "task_id", "event_type", "status", "attempt_count", "created_at"],
        "feedback": ["email_id", "label", "note", "created_at"],
        "runs": ["run_id", "status", "received_count", "processed", "tasks_created", "tasks_updated", "skipped", "unchanged"],
    }
    try:
        return ChatPlan(intent="analytics", analytics=AnalyticsQuery(
            dataset=dataset,
            operation=operation_name,
            filters=filters,
            group_by=group_by,
            metric=metric,
            fields=default_fields[dataset] if operation_name == "list" else [],
        ))
    except ValueError:
        # Conflicting language such as "tasks by run status" may resolve to a
        # cross-dataset field. Fail closed and let the validated model planner
        # clarify it when configured.
        return None


def plan_question(question: str) -> ChatPlan:
    """Map supported natural-language questions to a closed, read-only query plan.

    The planner intentionally never emits SQL or arbitrary field names. Synonyms
    cover the question families from the challenge while unknown questions fail
    closed instead of being answered from guesses.
    """
    q = _normalize(question)

    if _requests_action(q):
        return ChatPlan(intent="out_of_scope")

    # Owner names are a compound-filter signal that the legacy one-purpose
    # intents cannot represent. Route them through the general typed query.
    if any(re.search(rf"\b{re.escape(alias)}\b", q) for alias in ASSIGNEE_ALIASES):
        return _general_analytics_plan(q) or ChatPlan(intent="unsupported")

    if _has_any(q, ("spurious", "false positive", "incorrectly escalated", "incorrectly routed", "junk task")):
        return ChatPlan(intent="spurious_rate")

    thread_terms = ("thread", "threads", "conversation", "conversations")
    repeat_terms = (
        "updated more than once", "changed more than once", "more than one update",
        "at least twice", "updated twice", "changed twice", "multiple updates", "multiple times",
    )
    if _has_any(q, thread_terms) and _has_any(q, repeat_terms):
        return ChatPlan(intent="threads_with_updates")

    total_terms = ("total", "sum", "add up", "combined", "aggregate", "worth")
    value_terms = ("deal value", "deal values", "value of", "opportunity value", "value", "budget")
    rfp_terms = ("rfp", "rfps", "proposal", "proposals", "tender", "tenders")
    if _has_any(q, total_terms) and _has_any(q, value_terms) and _has_any(q, rfp_terms):
        return ChatPlan(intent="sum_deal_value", categories=["enterprise_rfp"])

    triage_terms = ("triage", "manual review", "ambiguous", "unassigned queue")
    if _has_any(q, triage_terms) and _has_any(q, ("list", "which", "what", "why", "show", "everything")):
        return ChatPlan(intent="list_triage")

    priority_terms = ("high priority", "high-priority", "urgent")
    confidence_terms = ("low confidence", "poor confidence", "low certainty", "uncertain", "unassigned-feeling", "routing certainty")
    if _has_any(q, priority_terms) and _has_any(q, confidence_terms):
        return ChatPlan(intent="list_priority_confidence", priority="high", max_confidence=0.54)

    if "gst" in q and _has_any(q, ("refund", "refunds")):
        return ChatPlan(intent="count_topic", topic="gst_refund")

    alliance_terms = ("alliance", "alliances", "partnership", "partnerships", "partner emails")
    alliance_subtype_terms = ("reseller", "resellers", "channel", "integration", "integrations", "subtype", "break down", "breakdown", "versus", " vs ")
    if _has_any(q, alliance_terms) and _has_any(q, alliance_subtype_terms):
        return ChatPlan(intent="count_subtypes", categories=["alliances"])

    marketing_terms = ("marketing", "sponsorship", "sponsorships", "webinar", "webinars")
    spam_terms = ("spam", "vendor", "seo pitch", "seo pitches", "discarded", "ignored", "skipped")
    if _has_any(q, marketing_terms) and _has_any(q, spam_terms):
        return ChatPlan(intent="compare_category_and_skip_reason", categories=["marketing"], skip_reasons=["vendor_spam"])

    count_terms = ("how many", "count", "number", "were there", "any")
    if _has_any(q, marketing_terms) and _has_any(q, rfp_terms) and _has_any(q, count_terms + ("versus", " vs ", "compare")):
        return ChatPlan(intent="compare_categories", categories=["enterprise_rfp", "marketing"])

    if _has_any(q, rfp_terms) and _has_any(q, count_terms):
        return ChatPlan(intent="count_category", categories=["enterprise_rfp"])

    general_plan = _general_analytics_plan(q)
    return general_plan or ChatPlan(intent="unsupported")
