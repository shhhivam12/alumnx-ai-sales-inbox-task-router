from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from backend.app.domain.email_models import NormalizedEmail
from backend.app.domain.enums import Operation
from backend.app.domain.task_models import RoutingDecision, TaskPatch
from backend.app.errors import AppError
from backend.app.repositories.store import MemoryStore
from backend.app.services.task_api_client import TaskApi


MUTABLE_FIELDS = ("title", "description", "assignee_id", "category", "priority", "due_date", "deal_value_inr", "company_name", "confidence")


def remote_id(task: dict[str, Any] | None) -> str | None:
    return (task or {}).get("task_id") or (task or {}).get("id")


def _operation_key(message: NormalizedEmail, kind: str) -> str:
    return f"{message.email.thread_id}:{message.email.email_id}:{kind}"


class Reconciler:
    def __init__(self, store: MemoryStore, task_api: TaskApi) -> None:
        self.store = store
        self.task_api = task_api

    def reconcile(self, message: NormalizedEmail, decision: RoutingDecision, run_id: str) -> str:
        with self.store.thread_lock(message.email.thread_id):
            if self.store.inspect_email(message) == "unchanged":
                return "unchanged"
            thread = self.store.get_thread(message.email.thread_id)
            if decision.operation == Operation.SKIP:
                self.store.save_outcome(message, decision, run_id, thread.get("current_task_snapshot") if thread else None, None)
                return "skipped"
            if decision.operation == Operation.NOOP:
                event = self._event(message, "noop", thread.get("current_task_snapshot") if thread else None, None, thread.get("current_task_snapshot") if thread else None)
                self.store.save_outcome(message, decision, run_id, thread.get("current_task_snapshot") if thread else None, event)
                return "noop"
            if not decision.task:
                raise AppError("missing_task_payload", "actionable decision has no task payload", status_code=500)

            remote_matches = self.task_api.list_tasks(thread_id=message.email.thread_id)
            if len(remote_matches) > 1:
                raise AppError("remote_task_conflict", "multiple remote tasks exist for one thread", status_code=409)
            remote = remote_matches[0] if remote_matches else None
            mapped_id = thread.get("remote_task_id") if thread else None
            if mapped_id and remote is None:
                mapped = self.task_api.get_task(mapped_id)
                if mapped is None:
                    raise AppError("remote_task_missing", "previously mapped remote task is missing", status_code=502)
                remote = mapped

            has_local_predecessor = bool(thread and thread.get("last_message_index", -1) >= 0)
            if message.email.message_index > 0 and not has_local_predecessor and not remote:
                raise AppError("orphan_reply", "reply has no stored predecessor or remote task", status_code=409)

            if remote is None:
                event = self._event(message, "create", None, decision.task.model_dump(mode="json"), None, status="pending")
                try:
                    remote = self.task_api.create_task(decision.task)
                except AppError:
                    # A timed-out POST may have succeeded; query before allowing another attempt.
                    discovered = self.task_api.list_tasks(thread_id=message.email.thread_id, source_email_id=decision.task.source_email_id)
                    if len(discovered) == 1:
                        remote = discovered[0]
                    else:
                        raise
                event.update(status="confirmed", remote_task_id=remote_id(remote), after_snapshot=remote, confirmed_at=datetime.now(timezone.utc).isoformat())
                self.store.save_outcome(message, decision, run_id, remote, event)
                return "created"

            desired = decision.task.model_dump(mode="json")
            patch_data = {field: desired.get(field) for field in MUTABLE_FIELDS if remote.get(field) != desired.get(field)}
            if not patch_data:
                decision.operation = Operation.NOOP
                event = self._event(message, "noop", remote, None, remote)
                self.store.save_outcome(message, decision, run_id, remote, event)
                return "noop"
            before = remote
            patch = TaskPatch.model_validate(patch_data)
            task_id = remote_id(remote)
            if not task_id:
                raise AppError("invalid_task_api_response", "remote task response has no task_id", status_code=502)
            after = self.task_api.patch_task(task_id, patch)
            decision.operation = Operation.UPDATE
            event = self._event(message, "update", before, patch.model_dump(mode="json", exclude_unset=True), after)
            self.store.save_outcome(message, decision, run_id, after, event)
            return "updated"

    @staticmethod
    def _event(message: NormalizedEmail, kind: str, before: dict[str, Any] | None, patch: dict[str, Any] | None, after: dict[str, Any] | None, status: str = "confirmed") -> dict[str, Any]:
        return {"id": str(uuid4()), "operation_key": _operation_key(message, kind), "thread_id": message.email.thread_id, "email_id": message.email.email_id, "remote_task_id": remote_id(after or before), "event_type": kind, "status": status, "before_snapshot": before, "patch": patch, "after_snapshot": after, "attempt_count": 1, "confirmed_at": datetime.now(timezone.utc).isoformat() if status == "confirmed" else None}
