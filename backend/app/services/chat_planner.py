from __future__ import annotations

import re
import unicodedata

from backend.app.domain.chat_models import ChatPlan


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
    )
    return any(re.search(pattern, text) for pattern in patterns)


def plan_question(question: str) -> ChatPlan:
    """Map supported natural-language questions to a closed, read-only query plan.

    The planner intentionally never emits SQL or arbitrary field names. Synonyms
    cover the question families from the challenge while unknown questions fail
    closed instead of being answered from guesses.
    """
    q = _normalize(question)

    if _requests_action(q):
        return ChatPlan(intent="out_of_scope")

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

    return ChatPlan(intent="unsupported")
