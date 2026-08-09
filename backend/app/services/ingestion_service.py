from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from uuid import UUID

from backend.app.config import Settings
from backend.app.domain.email_models import IngestError, IngestRequest, IngestResponse
from backend.app.domain.routing_policy import route_email
from backend.app.errors import AppError
from backend.app.repositories.store import MemoryStore
from backend.app.services.email_normalizer import normalize_email
from backend.app.services.gemini_extractor import GeminiExtractor
from backend.app.services.reconciler import Reconciler
from backend.app.services.suppression import deterministic_suppression


class IngestionService:
    def __init__(self, settings: Settings, store: MemoryStore, extractor: GeminiExtractor, reconciler: Reconciler) -> None:
        self.settings = settings
        self.store = store
        self.extractor = extractor
        self.reconciler = reconciler

    def ingest(self, request: IngestRequest) -> IngestResponse:
        request_hash = hashlib.sha256(json.dumps(request.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()
        run_id = self.store.start_run(request.client_batch_id, request.source, request_hash, len(request.emails))
        counters = {"processed": 0, "tasks_created": 0, "tasks_updated": 0, "skipped": 0, "unchanged": 0}
        errors: list[IngestError] = []
        grouped = defaultdict(list)
        for email in request.emails:
            grouped[email.thread_id].append(email)
        queues = {
            thread_id: sorted(items, key=lambda e: (e.message_index, e.received_at, e.email_id))
            for thread_id, items in grouped.items()
        }
        # A wave contains at most one message per thread. This permits five-way
        # semantic extraction while ensuring replies never overtake predecessors.
        while any(queues.values()):
            thread_ids = [thread_id for thread_id in sorted(queues) if queues[thread_id]][: self.settings.gemini_batch_size]
            wave = [queues[thread_id].pop(0) for thread_id in thread_ids]
            prepared = []
            for email in wave:
                normalized = normalize_email(email, self.settings.normalized_prompt_max_chars)
                try:
                    state = self.store.inspect_email(normalized)
                except AppError as exc:
                    self._handle_error(exc, email, run_id, counters, errors)
                    continue
                if state == "unchanged":
                    self.store.record_delivery(run_id, normalized, "unchanged")
                    counters["processed"] += 1
                    counters["unchanged"] += 1
                    continue
                prior = self.store.get_thread(email.thread_id)
                extraction = deterministic_suppression(normalized)
                prepared.append((email, normalized, prior, extraction))

            model_items = [item[1] for item in prepared if item[3] is None]
            model_results = self.extractor.extract_many(
                model_items,
                {item[0].thread_id: item[2].get("current_task_snapshot") if item[2] else None for item in prepared},
            ) if model_items else []
            model_by_id = {result.email_id: result for result in model_results}

            for email, normalized, prior, extraction in prepared:
                try:
                    extraction = extraction or model_by_id[email.email_id]
                    degraded = not bool(self.extractor._client) or extraction.reasoning_summary.startswith("Degraded")
                    decision = route_email(normalized, extraction, prior_task=prior.get("current_task_snapshot") if prior else None, degraded=degraded, prompt_version=self.settings.routing_prompt_version, model_name=self.settings.gemini_model if self.extractor._client else None)
                    outcome = self.reconciler.reconcile(normalized, decision, run_id)
                    if outcome == "unchanged":
                        # Another request may have persisted this email after the
                        # optimistic pre-check but before the thread lock.
                        self.store.record_delivery(run_id, normalized, "unchanged")
                    counters["processed"] += 1
                    if outcome == "created": counters["tasks_created"] += 1
                    elif outcome == "updated": counters["tasks_updated"] += 1
                    elif outcome == "skipped": counters["skipped"] += 1
                    elif outcome == "unchanged": counters["unchanged"] += 1
                except AppError as exc:
                    self._handle_error(exc, email, run_id, counters, errors)
                except Exception as exc:
                    errors.append(IngestError(email_id=email.email_id, thread_id=email.thread_id, stage="processing", code="internal_error", message=str(exc)))
                    self.store.finish_run(run_id, counters, [error.model_dump(mode="json") for error in errors])
                    raise AppError(
                        "internal_error", "email processing failed", status_code=500,
                        details={"email_id": email.email_id, "thread_id": email.thread_id, "stage": "processing"},
                    ) from exc
        self.store.finish_run(run_id, counters, [e.model_dump(mode="json") for e in errors])
        return IngestResponse(run_id=UUID(run_id), errors=errors, **counters)

    def _handle_error(self, exc: AppError, email, run_id: str, counters: dict, errors: list[IngestError]) -> None:
        errors.append(IngestError(email_id=email.email_id, thread_id=email.thread_id, stage="processing", code=exc.code, message=exc.message, retryable=exc.retryable))
        self.store.finish_run(run_id, counters, [error.model_dump(mode="json") for error in errors])
        raise AppError(exc.code, exc.message, status_code=exc.status_code, retryable=exc.retryable, details={"email_id": email.email_id, "thread_id": email.thread_id, "stage": "processing"})
