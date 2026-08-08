from __future__ import annotations

from collections import Counter
from typing import Any

from backend.app.repositories.store import MemoryStore


class StatsService:
    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def get(self, scope_type: str = "all", scope_id: str | None = None) -> dict[str, Any]:
        decisions = self.store.list_decisions(scope_type, scope_id)
        runs = self.store.list_runs(scope_type, scope_id)
        thread_ids = {decision["thread_id"] for decision in decisions}
        emails = len({d["email_id"] for d in decisions})
        operations = Counter(d["operation"] for d in decisions)
        categories = Counter((d.get("task") or {}).get("category") for d in decisions if d.get("task"))
        assignees = Counter((d.get("task") or {}).get("assignee_id") for d in decisions if d.get("task"))
        priorities = Counter((d.get("task") or {}).get("priority") for d in decisions if d.get("task"))
        skips = Counter(d.get("skip_reason") for d in decisions if d.get("skip_reason"))
        spurious = sum(1 for f in self.store.list_feedback() if f["label"] == "spurious" and any(d["email_id"] == f["email_id"] for d in decisions))
        update_counts = Counter(e["thread_id"] for e in self.store.list_events() if e["thread_id"] in thread_ids and e["event_type"] == "update" and e["status"] == "confirmed")
        return {
            "unique_processed": emails,
            "current_tasks": sum(1 for thread in self.store.list_threads() if thread["thread_id"] in thread_ids and thread.get("current_task_snapshot")),
            "delivery_attempts": sum(r.get("received_count", 0) for r in runs),
            "created": operations["create"], "updated": operations["update"], "skipped": operations["skip"],
            "noop": operations["noop"], "unchanged": sum(r.get("unchanged", 0) for r in runs),
            "errors": sum(len(r.get("errors", [])) for r in runs),
            "by_category": dict(categories), "by_assignee": dict(assignees), "by_priority": dict(priorities), "by_skip_reason": dict(skips),
            "confirmed_spurious_count": spurious,
            "confirmed_spurious_rate": round(spurious / emails, 4) if emails else 0,
            "low_confidence_count": sum(1 for d in decisions if float(d.get("confidence", 1)) <= .54),
            "update_event_total": sum(update_counts.values()),
            "threads_updated_more_than_once": sum(1 for count in update_counts.values() if count > 1),
        }
