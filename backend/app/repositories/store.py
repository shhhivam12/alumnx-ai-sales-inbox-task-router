from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from typing import Any
from uuid import UUID, uuid4

from backend.app.domain.email_models import NormalizedEmail
from backend.app.domain.task_models import RoutingDecision
from backend.app.errors import AppError


class MemoryStore:
    """Thread-safe baseline store used by unit tests and credential-free local demos."""

    def __init__(self) -> None:
        self.emails: dict[str, dict[str, Any]] = {}
        self.thread_indexes: dict[tuple[str, int], str] = {}
        self.threads: dict[str, dict[str, Any]] = {}
        self.decisions: dict[str, dict[str, Any]] = {}
        self.events: list[dict[str, Any]] = []
        self.runs: dict[str, dict[str, Any]] = {}
        self.groups: dict[str, dict[str, Any]] = {}
        self.feedback: dict[str, dict[str, Any]] = {}
        self.chat_audit: list[dict[str, Any]] = []
        self._locks: defaultdict[str, RLock] = defaultdict(RLock)
        self._global = RLock()

    def health(self) -> bool:
        return True

    def migration_ready(self) -> bool:
        return True

    def start_run(self, client_batch_id: UUID | None, source: str, request_hash: str, count: int) -> str:
        with self._global:
            group_id = None
            if client_batch_id:
                key = str(client_batch_id)
                self.groups.setdefault(key, {"id": str(uuid4()), "client_batch_id": key, "source": source})
                group_id = self.groups[key]["id"]
            run_id = str(uuid4())
            self.runs[run_id] = {"id": run_id, "group_id": group_id, "client_batch_id": str(client_batch_id) if client_batch_id else None, "status": "processing", "received_count": count, "started_at": datetime.now(timezone.utc).isoformat()}
            return run_id

    def finish_run(self, run_id: str, counters: dict[str, int], errors: list[dict[str, Any]]) -> None:
        self.runs[run_id].update(counters | {"errors": errors, "status": "failed" if errors else "completed", "completed_at": datetime.now(timezone.utc).isoformat()})

    def inspect_email(self, message: NormalizedEmail) -> str:
        with self._global:
            prior = self.emails.get(message.email.email_id)
            if prior:
                if prior["content_hash"] != message.content_hash:
                    raise AppError("email_id_content_conflict", "stored email_id has different content", status_code=409, path="email_id")
                return "unchanged"
            key = (message.email.thread_id, message.email.message_index)
            if key in self.thread_indexes and self.thread_indexes[key] != message.email.email_id:
                raise AppError("thread_index_conflict", "thread/message_index already belongs to another email", status_code=409)
            return "new"

    def thread_lock(self, thread_id: str) -> RLock:
        return self._locks[thread_id]

    def get_thread(self, thread_id: str) -> dict[str, Any] | None:
        return deepcopy(self.threads.get(thread_id))

    def save_outcome(self, message: NormalizedEmail, decision: RoutingDecision, run_id: str, remote: dict[str, Any] | None, event: dict[str, Any] | None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._global:
            self.emails[message.email.email_id] = {"email": message.email.model_dump(mode="json"), "content_hash": message.content_hash, "normalized_body": message.normalized_body, "latest_reply_body": message.latest_reply_body, "run_id": run_id}
            self.thread_indexes[(message.email.thread_id, message.email.message_index)] = message.email.email_id
            run = self.runs[run_id]
            task_id = (remote or {}).get("task_id") or (remote or {}).get("id")
            record = decision.model_dump(mode="json") | {"run_id": run_id, "group_id": run.get("group_id"), "client_batch_id": run.get("client_batch_id"), "created_at": now, "remote_task_id": task_id}
            self.decisions[message.email.email_id] = record
            prior = self.threads.get(message.email.thread_id, {})
            update_count = prior.get("update_count", 0) + (1 if decision.operation.value == "update" and event else 0)
            self.threads[message.email.thread_id] = {"thread_id": message.email.thread_id, "remote_task_id": task_id or prior.get("remote_task_id"), "source_email_id": (remote or prior).get("source_email_id"), "current_task_snapshot": deepcopy(remote or prior.get("current_task_snapshot")), "last_message_index": max(message.email.message_index, prior.get("last_message_index", -1)), "message_count": prior.get("message_count", 0) + 1, "update_count": update_count, "updated_at": now}
            if event:
                self.events.append(event | {"created_at": now, "run_id": run_id})

    def list_decisions(self, scope_type: str = "all", scope_id: str | None = None) -> list[dict[str, Any]]:
        rows = list(self.decisions.values())
        if scope_type == "run":
            rows = [r for r in rows if r["run_id"] == scope_id]
        elif scope_type == "batch":
            rows = [r for r in rows if r.get("client_batch_id") == scope_id]
        return deepcopy(rows)

    def list_threads(self) -> list[dict[str, Any]]:
        return deepcopy(list(self.threads.values()))

    def list_events(self) -> list[dict[str, Any]]:
        return deepcopy(self.events)

    def list_runs(self, scope_type: str = "all", scope_id: str | None = None) -> list[dict[str, Any]]:
        rows = list(self.runs.values())
        if scope_type == "run": rows = [r for r in rows if r["id"] == scope_id]
        if scope_type == "batch": rows = [r for r in rows if r.get("client_batch_id") == scope_id]
        return deepcopy(rows)

    def set_feedback(self, email_id: str, label: str, note: str | None) -> dict[str, Any]:
        if email_id not in self.decisions:
            raise AppError("decision_not_found", "email decision not found", status_code=404)
        row = {"email_id": email_id, "label": label, "note": note, "created_at": datetime.now(timezone.utc).isoformat()}
        self.feedback[email_id] = row
        return row

    def list_feedback(self) -> list[dict[str, Any]]:
        return deepcopy(list(self.feedback.values()))

    def add_chat_audit(self, row: dict[str, Any]) -> None:
        self.chat_audit.append(deepcopy(row))
