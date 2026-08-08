from __future__ import annotations

from backend.app.domain.chat_models import ChatPlan


def plan_question(question: str) -> ChatPlan:
    q = question.lower().strip()
    if any(term in q for term in ("send an email", "email them", "delete task", "create task")):
        return ChatPlan(intent="out_of_scope")
    if "spurious" in q:
        return ChatPlan(intent="spurious_rate")
    if "updated more than once" in q or ("threads" in q and "updates" in q):
        return ChatPlan(intent="threads_with_updates")
    if "total" in q and any(term in q for term in ("deal value", "value of")):
        return ChatPlan(intent="sum_deal_value", categories=["enterprise_rfp"] if "rfp" in q or "proposal" in q else [])
    if "triage" in q and any(term in q for term in ("list", "which", "why", "show")):
        return ChatPlan(intent="list_triage")
    if "high" in q and "confidence" in q:
        return ChatPlan(intent="list_priority_confidence", priority="high", max_confidence=.54)
    if "gst refund" in q:
        return ChatPlan(intent="count_topic", topic="gst_refund")
    if "alliance" in q and "subtype" in q:
        return ChatPlan(intent="count_subtypes", categories=["alliances"])
    if "alliance" in q and "reseller" in q and ("integration" in q or "versus" in q):
        return ChatPlan(intent="count_subtypes", categories=["alliances"])
    if "marketing" in q and any(term in q for term in ("spam", "vendor")):
        return ChatPlan(intent="compare_category_and_skip_reason", categories=["marketing"], skip_reasons=["vendor_spam"])
    if "marketing" in q and any(term in q for term in ("rfp", "proposal")) and any(term in q for term in ("versus", " vs ", "compare")):
        return ChatPlan(intent="compare_categories", categories=["enterprise_rfp", "marketing"])
    if any(term in q for term in ("rfp", "proposal", "tender")) and any(term in q for term in ("how many", "count", "number")):
        return ChatPlan(intent="count_category", categories=["enterprise_rfp"])
    return ChatPlan(intent="unsupported")
