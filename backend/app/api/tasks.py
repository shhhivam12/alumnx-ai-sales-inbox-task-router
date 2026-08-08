from typing import Any

from fastapi import APIRouter, Depends, Query

from backend.app.dependencies import get_store
from backend.app.domain.enums import AssigneeId, Category, Priority
from backend.app.errors import AppError
from backend.app.repositories.store import MemoryStore

router = APIRouter(tags=["tasks"])


@router.get("/tasks")
def tasks(
    batch_id: str | None = None, run_id: str | None = None, thread_id: str | None = None,
    assignee_id: AssigneeId | None = None, category: Category | None = None, priority: Priority | None = None,
    confidence_lte: float | None = Query(default=None, ge=0, le=1), confidence_gte: float | None = Query(default=None, ge=0, le=1),
    store: MemoryStore = Depends(get_store),
) -> dict[str, Any]:
    if confidence_lte is not None and confidence_gte is not None and confidence_gte > confidence_lte:
        raise AppError("invalid_confidence_range", "confidence_gte cannot exceed confidence_lte", path="confidence_gte")
    scope_type, scope_id = ("run", run_id) if run_id else (("batch", batch_id) if batch_id else ("all", None))
    decisions = store.list_decisions(scope_type, scope_id)
    # This endpoint represents current grader-visible tasks, not one row per historical
    # decision. Keep the latest decision for each thread in the selected scope.
    latest_by_thread = {}
    for decision in decisions:
        if decision.get("task"):
            latest_by_thread[decision["thread_id"]] = decision
    items = []
    for decision in latest_by_thread.values():
        task = decision.get("task")
        if not task: continue
        if thread_id and decision["thread_id"] != thread_id: continue
        if assignee_id and task.get("assignee_id") != assignee_id.value: continue
        if category and task.get("category") != category.value: continue
        if priority and task.get("priority") != priority.value: continue
        if confidence_lte is not None and decision["confidence"] > confidence_lte: continue
        if confidence_gte is not None and decision["confidence"] < confidence_gte: continue
        current = store.get_task(decision["remote_task_id"]) if decision.get("remote_task_id") else task
        if current:
            items.append({"task": current, "decision": {"reasoning": decision["reasoning"], "evidence": decision["evidence"], "confidence": decision["confidence"], "run_id": decision["run_id"], "update_count": (store.get_thread(decision["thread_id"]) or {}).get("update_count", 0)}})
    return {"items": items, "total": len(items), "warning": None}
