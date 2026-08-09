from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from backend.app.domain.chat_models import AnalyticsFilter, AnalyticsQuery, ChatPlan, ChatScope
from backend.app.repositories.store import MemoryStore


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    return value


def _scoped_records(store: MemoryStore, scope: ChatScope) -> dict[str, list[dict[str, Any]]]:
    decisions = store.list_decisions(scope.type, scope.id)
    thread_ids = {decision["thread_id"] for decision in decisions}
    threads = [thread for thread in store.list_threads() if thread["thread_id"] in thread_ids]
    thread_by_id = {thread["thread_id"]: thread for thread in threads}
    latest_task_decision: dict[str, dict[str, Any]] = {}
    latest_decision: dict[str, dict[str, Any]] = {}
    for decision in decisions:
        latest_decision[decision["thread_id"]] = decision
        if decision.get("task"):
            latest_task_decision[decision["thread_id"]] = decision

    current_tasks = []
    for thread_id, thread in thread_by_id.items():
        decision = latest_task_decision.get(thread_id) or latest_decision[thread_id]
        task_id = thread.get("remote_task_id") or decision.get("remote_task_id")
        live_task = store.get_task(task_id) if task_id else None
        task = live_task or thread.get("current_task_snapshot") or decision.get("task") or {}
        if not task:
            continue
        current_tasks.append(_json_value({
            **task,
            "task_id": task_id or task.get("task_id"),
            "email_id": decision.get("email_id"),
            "source_email_id": task.get("source_email_id") or decision.get("email_id"),
            "thread_id": thread_id,
            "reasoning": decision.get("reasoning"),
            "evidence": decision.get("evidence", []),
            "run_id": decision.get("run_id"),
            "client_batch_id": decision.get("client_batch_id"),
            "message_count": thread.get("message_count"),
            "update_count": thread.get("update_count"),
            "last_message_index": thread.get("last_message_index"),
            "updated_at": thread.get("updated_at"),
        }))

    decision_records = []
    for decision in decisions:
        task = decision.get("task") or {}
        decision_records.append(_json_value({
            **decision,
            **task,
            "task_id": decision.get("remote_task_id") or task.get("task_id"),
            "source_email_id": task.get("source_email_id") or decision.get("email_id"),
        }))

    thread_records = []
    for thread in threads:
        task = thread.get("current_task_snapshot") or {}
        thread_records.append(_json_value({
            **thread,
            **task,
            "task_id": thread.get("remote_task_id") or task.get("task_id"),
        }))

    event_records = []
    for event in store.list_events():
        if event.get("thread_id") in thread_ids:
            event_records.append(_json_value({**event, "task_id": event.get("remote_task_id")}))

    email_ids = {decision["email_id"] for decision in decisions}
    feedback_records = [_json_value(row) for row in store.list_feedback() if row.get("email_id") in email_ids]
    run_records = []
    for run in store.list_runs(scope.type, scope.id):
        run_records.append(_json_value({**run, "run_id": str(run.get("id") or run.get("run_id"))}))

    return {
        "current_tasks": current_tasks,
        "decisions": decision_records,
        "threads": thread_records,
        "events": event_records,
        "feedback": feedback_records,
        "runs": run_records,
    }


def _comparable(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        try:
            return float(stripped)
        except ValueError:
            return stripped.casefold()
    return value


def _matches_filter(record: dict[str, Any], query_filter: AnalyticsFilter) -> bool:
    actual = record.get(query_filter.field)
    expected = query_filter.value
    operator = query_filter.operator
    if operator == "is_null":
        return actual is None
    if operator == "not_null":
        return actual is not None
    if actual is None:
        return False
    if operator == "contains":
        if isinstance(actual, list):
            return any(_comparable(item) == _comparable(expected) for item in actual)
        return str(expected).casefold() in str(actual).casefold()
    if operator == "in":
        choices = expected if isinstance(expected, list) else [expected]
        if isinstance(actual, list):
            return any(_comparable(item) in {_comparable(choice) for choice in choices} for item in actual)
        return _comparable(actual) in {_comparable(choice) for choice in choices}
    left, right = _comparable(actual), _comparable(expected)
    if operator == "eq":
        return left == right
    if operator == "neq":
        return left != right
    try:
        if operator == "gte": return left >= right
        if operator == "lte": return left <= right
        if operator == "gt": return left > right
        if operator == "lt": return left < right
    except TypeError:
        return False
    return False


def _execute_analytics(store: MemoryStore, query: AnalyticsQuery, scope: ChatScope) -> dict[str, Any]:
    rows = _scoped_records(store, scope)[query.dataset]
    matches = [row for row in rows if all(_matches_filter(row, item) for item in query.filters)]
    base: dict[str, Any] = {
        "dataset": query.dataset,
        "operation": query.operation,
        "filters": [item.model_dump(mode="json") for item in query.filters],
        "total_matches": len(matches),
    }
    if query.operation == "count":
        return base | {"count": len(matches)}
    if query.operation == "list":
        fields = query.fields
        items = [
            {field: row.get(field) for field in fields if row.get(field) is not None}
            for row in matches[:query.limit]
        ]
        return base | {"count": len(matches), "shown": len(items), "items": items, "limit": query.limit}
    if query.operation == "group_count":
        groups = Counter(str(row.get(query.group_by) if row.get(query.group_by) is not None else "unavailable") for row in matches)
        return base | {"group_by": query.group_by, "groups": dict(sorted(groups.items()))}

    values = [row.get(query.metric) for row in matches]
    numeric_values = [float(value) for value in values if isinstance(value, (int, float)) and not isinstance(value, bool)]
    missing = len(values) - len(numeric_values)
    if query.operation == "sum":
        result = sum(numeric_values)
    elif query.operation == "average":
        result = sum(numeric_values) / len(numeric_values) if numeric_values else None
    elif query.operation == "minimum":
        result = min(numeric_values) if numeric_values else None
    else:
        result = max(numeric_values) if numeric_values else None
    if result is not None and float(result).is_integer():
        result = int(result)
    return base | {
        "metric": query.metric,
        "value": result,
        "values_used": len(numeric_values),
        "missing_values": missing,
    }


def execute_plan(store: MemoryStore, plan: ChatPlan, scope: ChatScope) -> dict[str, Any]:
    if plan.intent == "analytics":
        return _execute_analytics(store, plan.analytics, scope)
    decisions = store.list_decisions(scope.type, scope.id)
    actionable_by_thread = {}
    for decision in decisions:
        if decision.get("task"):
            actionable_by_thread[decision["thread_id"]] = decision
    thread_ids = {decision["thread_id"] for decision in decisions}
    current_threads = [thread for thread in store.list_threads() if thread["thread_id"] in thread_ids]
    if plan.intent == "count_category":
        category = plan.categories[0]
        count = sum(1 for d in decisions if (d.get("task") or {}).get("category") == category)
        return {"category": category, "count": count, category: count}
    if plan.intent == "compare_categories":
        return {category: sum(1 for d in decisions if (d.get("task") or {}).get("category") == category) for category in plan.categories}
    if plan.intent == "compare_category_and_skip_reason":
        category, reason = plan.categories[0], plan.skip_reasons[0]
        routed_count = sum(1 for d in decisions if (d.get("task") or {}).get("category") == category)
        skipped_count = sum(1 for d in decisions if d.get("skip_reason") == reason)
        return {
            "category": category,
            "routed_count": routed_count,
            "skip_reason": reason,
            "skipped_count": skipped_count,
            "marketing": routed_count,
            "skipped_marketing_lookalike_spam": skipped_count,
        }
    if plan.intent == "list_triage":
        items = []
        for thread in current_threads:
            task = thread.get("current_task_snapshot") or {}
            decision = actionable_by_thread.get(thread["thread_id"], {})
            if task.get("category") == "triage":
                items.append({"task_id": thread.get("remote_task_id"), "email_id": decision.get("email_id"), "thread_id": thread["thread_id"], "confidence": task.get("confidence"), "reason": decision.get("reasoning", task.get("description"))})
        return {
            "count": len(items),
            "items": items,
            "triage_count": len(items),
            "triage_task_ids": [item["task_id"] for item in items],
        }
    if plan.intent == "spurious_rate":
        flags = [f for f in store.list_feedback() if f["label"] == "spurious"]
        denominator = len({d["email_id"] for d in decisions})
        count = sum(1 for f in flags if any(d["email_id"] == f["email_id"] for d in decisions))
        rate = round(count / denominator, 4) if denominator else 0
        return {
            "confirmed_spurious": count,
            "unique_processed": denominator,
            "rate": rate,
            "spurious_count": count,
            "processed": denominator,
            "spurious_rate": rate,
        }
    if plan.intent == "list_priority_confidence":
        items = []
        for thread in current_threads:
            task = thread.get("current_task_snapshot") or {}
            if task.get("priority") == plan.priority and float(task.get("confidence", 1)) <= (plan.max_confidence or 1):
                items.append({"task_id": thread.get("remote_task_id"), "thread_id": thread["thread_id"], "confidence": task.get("confidence")})
        return {
            "priority": plan.priority,
            "confidence_lte": plan.max_confidence,
            "count": len(items),
            "items": items,
            "matches": items,
        }
    if plan.intent == "count_subtypes":
        rows = [d for d in decisions if (d.get("task") or {}).get("category") in plan.categories]
        counts = Counter(d.get("alliance_subtype") or "unavailable" for d in rows)
        return {"count": len(rows), "alliances": len(rows), "by_subtype": dict(counts)}
    if plan.intent == "count_topic":
        count = sum(1 for d in decisions if plan.topic in d.get("topics", []))
        return {"topic": plan.topic, "count": count, f"{plan.topic}_count": count}
    if plan.intent == "sum_deal_value":
        tasks = [thread.get("current_task_snapshot") or {} for thread in current_threads]
        tasks = [task for task in tasks if task and (not plan.categories or task.get("category") in plan.categories)]
        values = [task.get("deal_value_inr") for task in tasks]
        missing_value = sum(v is None for v in values)
        return {
            "category": plan.categories[0] if plan.categories else None,
            "total_deal_value_inr": sum(v for v in values if v is not None),
            "tasks_without_value": missing_value,
            "rfps_with_no_stated_value": missing_value,
            "task_count": len(tasks),
        }
    if plan.intent == "threads_with_updates":
        counts = Counter(e["thread_id"] for e in store.list_events() if e["thread_id"] in thread_ids and e["event_type"] == "update" and e["status"] == "confirmed")
        items = [{"thread_id": tid, "update_count": count} for tid, count in counts.items() if count > 1]
        return {
            "count": len(items),
            "items": items,
            "threads_updated_multiple_times": [item["thread_id"] for item in items],
        }
    return {}
