from __future__ import annotations

from collections import Counter
from typing import Any

from backend.app.domain.chat_models import ChatPlan, ChatScope
from backend.app.repositories.store import MemoryStore


def execute_plan(store: MemoryStore, plan: ChatPlan, scope: ChatScope) -> dict[str, Any]:
    decisions = store.list_decisions(scope.type, scope.id)
    actionable_by_thread = {}
    for decision in decisions:
        if decision.get("task"):
            actionable_by_thread[decision["thread_id"]] = decision
    thread_ids = {decision["thread_id"] for decision in decisions}
    current_threads = [thread for thread in store.list_threads() if thread["thread_id"] in thread_ids]
    if plan.intent == "count_category":
        category = plan.categories[0]
        return {"category": category, "count": sum(1 for d in decisions if (d.get("task") or {}).get("category") == category)}
    if plan.intent == "compare_categories":
        return {category: sum(1 for d in decisions if (d.get("task") or {}).get("category") == category) for category in plan.categories}
    if plan.intent == "compare_category_and_skip_reason":
        category, reason = plan.categories[0], plan.skip_reasons[0]
        return {"category": category, "routed_count": sum(1 for d in decisions if (d.get("task") or {}).get("category") == category), "skip_reason": reason, "skipped_count": sum(1 for d in decisions if d.get("skip_reason") == reason)}
    if plan.intent == "list_triage":
        items = []
        for thread in current_threads:
            task = thread.get("current_task_snapshot") or {}
            decision = actionable_by_thread.get(thread["thread_id"], {})
            if task.get("category") == "triage":
                items.append({"task_id": thread.get("remote_task_id"), "email_id": decision.get("email_id"), "thread_id": thread["thread_id"], "confidence": task.get("confidence"), "reason": decision.get("reasoning", task.get("description"))})
        return {"count": len(items), "items": items}
    if plan.intent == "spurious_rate":
        flags = [f for f in store.list_feedback() if f["label"] == "spurious"]
        denominator = len({d["email_id"] for d in decisions})
        count = sum(1 for f in flags if any(d["email_id"] == f["email_id"] for d in decisions))
        return {"confirmed_spurious": count, "unique_processed": denominator, "rate": round(count / denominator, 4) if denominator else 0}
    if plan.intent == "list_priority_confidence":
        items = []
        for thread in current_threads:
            task = thread.get("current_task_snapshot") or {}
            if task.get("priority") == plan.priority and float(task.get("confidence", 1)) <= (plan.max_confidence or 1):
                items.append({"task_id": thread.get("remote_task_id"), "thread_id": thread["thread_id"], "confidence": task.get("confidence")})
        return {"priority": plan.priority, "confidence_lte": plan.max_confidence, "count": len(items), "items": items}
    if plan.intent == "count_subtypes":
        rows = [d for d in decisions if (d.get("task") or {}).get("category") in plan.categories]
        counts = Counter(d.get("alliance_subtype") or "unavailable" for d in rows)
        return {"count": len(rows), "by_subtype": dict(counts)}
    if plan.intent == "count_topic":
        return {"topic": plan.topic, "count": sum(1 for d in decisions if plan.topic in d.get("topics", []))}
    if plan.intent == "sum_deal_value":
        tasks = [thread.get("current_task_snapshot") or {} for thread in current_threads]
        tasks = [task for task in tasks if task and (not plan.categories or task.get("category") in plan.categories)]
        values = [task.get("deal_value_inr") for task in tasks]
        return {"category": plan.categories[0] if plan.categories else None, "total_deal_value_inr": sum(v for v in values if v is not None), "tasks_without_value": sum(v is None for v in values), "task_count": len(tasks)}
    if plan.intent == "threads_with_updates":
        counts = Counter(e["thread_id"] for e in store.list_events() if e["thread_id"] in thread_ids and e["event_type"] == "update" and e["status"] == "confirmed")
        items = [{"thread_id": tid, "update_count": count} for tid, count in counts.items() if count > 1]
        return {"count": len(items), "items": items}
    return {}
