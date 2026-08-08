from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from dotenv import dotenv_values

from backend.app.config import LOCKED_CANDIDATE_ID, Settings
from backend.app.db.pool import DatabasePool
from backend.app.domain.email_models import EmailMessage
from backend.app.domain.enums import Actionability
from backend.app.domain.extraction_models import ExtractionResult, Intent
from backend.app.domain.routing_policy import route_email
from backend.app.domain.task_models import RoutingDecision
from backend.app.repositories.postgres_store import PostgresStore
from backend.app.services.email_normalizer import normalize_email
from backend.app.services.reconciler import Reconciler


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_SUPABASE_TESTS") != "1",
    reason="set RUN_SUPABASE_TESTS=1 to exercise the hosted development project",
)


def test_concurrent_identical_ingest_creates_one_atomic_task() -> None:
    root = Path(__file__).resolve().parents[3]
    url = dotenv_values(root / ".env").get("SUPABASE_DB_URL")
    assert url, "development SUPABASE_DB_URL is required"
    settings = Settings(supabase_db_url=str(url), supabase_migration_db_url="")
    pool = DatabasePool(settings)
    store = PostgresStore(pool)
    marker = uuid4().hex
    email_id, thread_id = f"concurrent-email-{marker}", f"concurrent-thread-{marker}"
    run_ids = [store.start_run(None, "api", marker + suffix, 1) for suffix in ("a", "b")]
    message = normalize_email(
        EmailMessage(
            email_id=email_id,
            thread_id=thread_id,
            message_index=0,
            from_name="Concurrent Buyer",
            from_email="buyer@example.com",
            to="sales@example.com",
            cc=[],
            subject="Product demo",
            body="Please arrange a product demo.",
            received_at=datetime.now(timezone.utc),
            attachments=[],
            is_reply=False,
        )
    )
    extraction = ExtractionResult(
        email_id=email_id,
        actionability=Actionability.ACTIONABLE,
        primary_intents=[Intent.DEMO_REQUEST],
        intent_direction="buying_from_us",
        reasoning_summary="Explicit demo request.",
    )
    template = route_email(message, extraction, model_name="fixture-concurrency")

    def reconcile(run_id: str) -> str:
        decision = RoutingDecision.model_validate(template.model_dump(mode="python"))
        return Reconciler(store).reconcile(message, decision, run_id)

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(reconcile, run_ids))
        assert sorted(outcomes) == ["created", "unchanged"]
        assert len(store.list_tasks(LOCKED_CANDIDATE_ID, thread_id=thread_id)) == 1
    finally:
        with pool.connection() as connection:
            connection.execute("DELETE FROM app_private.task_events WHERE candidate_id=%s AND email_id=%s", (LOCKED_CANDIDATE_ID, email_id))
            connection.execute("DELETE FROM app_private.decisions WHERE candidate_id=%s AND email_id=%s", (LOCKED_CANDIDATE_ID, email_id))
            connection.execute("DELETE FROM app_private.emails WHERE candidate_id=%s AND email_id=%s", (LOCKED_CANDIDATE_ID, email_id))
            connection.execute("DELETE FROM app_private.threads WHERE candidate_id=%s AND thread_id=%s", (LOCKED_CANDIDATE_ID, thread_id))
            connection.execute("DELETE FROM app_private.tasks WHERE candidate_id=%s AND thread_id=%s", (LOCKED_CANDIDATE_ID, thread_id))
            connection.execute("DELETE FROM app_private.ingest_runs WHERE id=ANY(%s)", (run_ids,))
            connection.commit()
        pool.close()
