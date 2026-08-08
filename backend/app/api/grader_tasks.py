from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response, status

from backend.app.config import LOCKED_CANDIDATE_ID
from backend.app.dependencies import get_store
from backend.app.domain.enums import AssigneeId
from backend.app.domain.task_models import TaskCreatedResponse, TaskPatch, TaskPayload, TaskRecord
from backend.app.errors import AppError


router = APIRouter(tags=["grader-task-api"])
ROSTER_PATH = Path(__file__).resolve().parents[3] / "data" / "team_roster.json"


def _candidate_id(value: str) -> str:
    normalized = value.strip().lower()
    if normalized != LOCKED_CANDIDATE_ID:
        raise AppError(
            "candidate_id_mismatch",
            "candidate_id does not match the configured submission identity",
            path="candidate_id",
        )
    return normalized


@router.post("/tasks", response_model=TaskCreatedResponse, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskPayload, store: Any = Depends(get_store)) -> dict[str, Any]:
    task = store.create_task(payload)
    return {
        "task_id": task["task_id"],
        "candidate_id": task["candidate_id"],
        "source_email_id": task["source_email_id"],
        "created_at": task["created_at"],
    }


@router.get("/tasks", response_model=list[TaskRecord])
def list_tasks(
    candidate_id: Annotated[str, Query(min_length=1)],
    thread_id: str | None = None,
    source_email_id: str | None = None,
    assignee_id: AssigneeId | None = None,
    store: Any = Depends(get_store),
) -> list[dict[str, Any]]:
    return store.list_tasks(
        _candidate_id(candidate_id),
        thread_id=thread_id,
        source_email_id=source_email_id,
        assignee_id=assignee_id.value if assignee_id else None,
    )


@router.patch("/tasks/{task_id}", response_model=TaskRecord)
def patch_task(task_id: str, patch: TaskPatch, store: Any = Depends(get_store)) -> dict[str, Any]:
    return store.patch_task(task_id, patch)


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: str, store: Any = Depends(get_store)) -> Response:
    if not store.delete_task(task_id):
        raise AppError("task_not_found", "task was not found", status_code=404)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/users")
def users() -> dict[str, Any]:
    return json.loads(ROSTER_PATH.read_text(encoding="utf-8"))
