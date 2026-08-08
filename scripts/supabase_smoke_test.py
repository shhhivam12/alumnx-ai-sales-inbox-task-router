from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from backend.app.config import LOCKED_CANDIDATE_ID, Settings
from backend.app.db.pool import DatabasePool
from backend.app.domain.email_models import EmailMessage
from backend.app.domain.enums import Actionability
from backend.app.domain.extraction_models import ExtractionResult, Intent
from backend.app.domain.routing_policy import route_email
from backend.app.repositories.postgres_store import PostgresStore
from backend.app.services.email_normalizer import normalize_email


def main() -> None:
    marker = uuid4().hex
    email_id = f"db-smoke-email-{marker}"
    thread_id = f"db-smoke-thread-{marker}"
    remote_task_id = f"db-smoke-task-{marker}"
    batch_id = uuid4()
    settings = Settings()
    pool = DatabasePool(settings)
    store = PostgresStore(pool)
    run_id: str | None = None
    smoke_passed = False

    try:
        message = normalize_email(
            EmailMessage(
                email_id=email_id,
                thread_id=thread_id,
                message_index=0,
                from_name="Database Smoke Buyer",
                from_email="buyer@example.com",
                to="sales@example.com",
                cc=[],
                subject="Development database smoke test",
                body="Please arrange a product demonstration. This is test data.",
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
            reasoning_summary="Explicit development smoke-test demo request.",
        )
        decision = route_email(message, extraction, model_name="fixture-smoke")
        run_id = store.start_run(batch_id, "api", marker, 1)
        remote = decision.task.model_dump(mode="json") | {"task_id": remote_task_id}
        event = {
            "id": str(uuid4()),
            "operation_key": f"create:{email_id}",
            "thread_id": thread_id,
            "email_id": email_id,
            "remote_task_id": remote_task_id,
            "event_type": "create",
            "status": "confirmed",
            "before_snapshot": None,
            "patch": None,
            "after_snapshot": remote,
            "attempt_count": 1,
            "confirmed_at": datetime.now(timezone.utc).isoformat(),
        }
        with store.thread_lock(thread_id):
            assert store.inspect_email(message) == "new"
            store.save_outcome(message, decision, run_id, remote, event)
        store.finish_run(
            run_id,
            {
                "processed": 1,
                "tasks_created": 1,
                "tasks_updated": 0,
                "skipped": 0,
                "unchanged": 0,
            },
            [],
        )
        store.set_feedback(email_id, "correct", "development smoke test")
        store.add_chat_audit(
            {
                "scope_type": "batch",
                "scope_id": str(batch_id),
                "question": "development smoke test",
                "validated_plan": {"intent": "count_category"},
                "supporting_data": {"count": 1},
                "answer": "1",
                "status": "answered",
            }
        )

        assert len(store.list_decisions("batch", str(batch_id))) == 1
        assert any(row["thread_id"] == thread_id for row in store.list_threads())
        assert any(row["email_id"] == email_id for row in store.list_events())
        assert any(row["email_id"] == email_id for row in store.list_feedback())
        smoke_passed = True
    finally:
        with pool.connection() as connection:
            connection.execute(
                "DELETE FROM app_private.chat_audit WHERE candidate_id=%s AND scope_id=%s",
                (LOCKED_CANDIDATE_ID, str(batch_id)),
            )
            connection.execute(
                "DELETE FROM app_private.quality_feedback WHERE candidate_id=%s AND email_id=%s",
                (LOCKED_CANDIDATE_ID, email_id),
            )
            connection.execute(
                "DELETE FROM app_private.task_events WHERE candidate_id=%s AND email_id=%s",
                (LOCKED_CANDIDATE_ID, email_id),
            )
            connection.execute(
                "DELETE FROM app_private.decisions WHERE candidate_id=%s AND email_id=%s",
                (LOCKED_CANDIDATE_ID, email_id),
            )
            connection.execute(
                "DELETE FROM app_private.emails WHERE candidate_id=%s AND email_id=%s",
                (LOCKED_CANDIDATE_ID, email_id),
            )
            connection.execute(
                "DELETE FROM app_private.threads WHERE candidate_id=%s AND thread_id=%s",
                (LOCKED_CANDIDATE_ID, thread_id),
            )
            if run_id:
                connection.execute("DELETE FROM app_private.ingest_runs WHERE id=%s", (run_id,))
            connection.execute(
                "DELETE FROM app_private.ingest_groups WHERE candidate_id=%s AND client_batch_id=%s",
                (LOCKED_CANDIDATE_ID, batch_id),
            )
            connection.commit()
            remaining = connection.execute(
                """
                SELECT
                    (SELECT count(*) FROM app_private.emails WHERE email_id=%s) +
                    (SELECT count(*) FROM app_private.threads WHERE thread_id=%s) +
                    (SELECT count(*) FROM app_private.task_events WHERE email_id=%s) +
                    (SELECT count(*) FROM app_private.quality_feedback WHERE email_id=%s) +
                    (SELECT count(*) FROM app_private.chat_audit WHERE scope_id=%s)
                    AS remaining
                """,
                (email_id, thread_id, email_id, email_id, str(batch_id)),
            ).fetchone()["remaining"]
            assert remaining == 0, "smoke-test cleanup left scoped rows behind"
        pool.close()
    if smoke_passed:
        print(
            "Supabase repository smoke passed: insert, lock, decision, event, "
            "feedback, audit, reads, and exact cleanup."
        )


if __name__ == "__main__":
    main()
