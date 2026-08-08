"""Exercise every public API group against the running production-configured backend.

All mutable records use a unique marker. The finally block removes only records
linked to that marker/batch and then proves that no matching rows remain.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import psycopg
from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "http://127.0.0.1:8000"
CANDIDATE_ID = "mahendrushivam123@gmail.com"


def assert_status(response: httpx.Response, status: int, label: str) -> Any:
    assert response.status_code == status, (
        f"{label}: expected {status}, received {response.status_code}: {response.text[:1000]}"
    )
    if status == 204:
        return None
    return response.json()


def email(marker: str, suffix: str, **changes: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "email_id": f"{marker}-email-{suffix}",
        "thread_id": f"{marker}-thread-{suffix}",
        "message_index": 0,
        "from_name": "Meridian Steel Procurement",
        "from_email": "procurement@meridiansteel.in",
        "to": "sales@example.com",
        "cc": [],
        "subject": "RFP - Enterprise DMS for Meridian Steel",
        "body": (
            "Meridian Steel invites proposals for an enterprise DMS. Indicative budget is "
            "Rs. 25 lakhs. Proposals must reach us by 12th August 2026."
        ),
        "received_at": "2026-08-01T09:00:00+05:30",
        "attachments": [],
        "is_reply": False,
    }
    item.update(changes)
    return item


def database_url() -> str:
    url = dotenv_values(ROOT / ".env").get("SUPABASE_DB_URL")
    if not url:
        raise SystemExit("SUPABASE_DB_URL is required")
    if "sslmode=" not in url:
        url += ("&" if "?" in url else "?") + "sslmode=require"
    return str(url)


def cleanup(marker: str, batch_id: str) -> dict[str, int]:
    pattern = marker + "%"
    deleted: dict[str, int] = {}
    with psycopg.connect(database_url(), connect_timeout=10) as connection:
        email_ids = [
            row[0]
            for row in connection.execute(
                "SELECT email_id FROM app_private.emails WHERE email_id LIKE %s", (pattern,)
            ).fetchall()
        ]
        thread_ids = [
            row[0]
            for row in connection.execute(
                "SELECT thread_id FROM app_private.threads WHERE thread_id LIKE %s", (pattern,)
            ).fetchall()
        ]
        group_ids = [
            row[0]
            for row in connection.execute(
                "SELECT id FROM app_private.ingest_groups WHERE client_batch_id=%s", (batch_id,)
            ).fetchall()
        ]
        run_ids = [
            row[0]
            for row in connection.execute(
                "SELECT id FROM app_private.ingest_runs WHERE group_id=ANY(%s)", (group_ids,)
            ).fetchall()
        ] if group_ids else []

        def remove(name: str, sql: str, params: tuple[Any, ...]) -> None:
            cursor = connection.execute(sql, params)
            deleted[name] = cursor.rowcount

        remove("feedback", "DELETE FROM app_private.quality_feedback WHERE email_id=ANY(%s)", (email_ids,))
        remove(
            "events",
            "DELETE FROM app_private.task_events WHERE email_id=ANY(%s) OR thread_id=ANY(%s)",
            (email_ids, thread_ids),
        )
        remove("decisions", "DELETE FROM app_private.decisions WHERE email_id=ANY(%s)", (email_ids,))
        remove("emails", "DELETE FROM app_private.emails WHERE email_id=ANY(%s)", (email_ids,))
        remove("threads", "DELETE FROM app_private.threads WHERE thread_id=ANY(%s)", (thread_ids,))
        remove(
            "tasks",
            "DELETE FROM app_private.tasks WHERE source_email_id LIKE %s OR thread_id LIKE %s",
            (pattern, pattern),
        )
        remove("chat", "DELETE FROM app_private.chat_audit WHERE scope_id=%s", (batch_id,))
        if run_ids:
            remove("runs", "DELETE FROM app_private.ingest_runs WHERE id=ANY(%s)", (run_ids,))
        if group_ids:
            remove("groups", "DELETE FROM app_private.ingest_groups WHERE id=ANY(%s)", (group_ids,))
        connection.commit()
        remaining = {
            "emails": connection.execute(
                "SELECT count(*) FROM app_private.emails WHERE email_id LIKE %s", (pattern,)
            ).fetchone()[0],
            "threads": connection.execute(
                "SELECT count(*) FROM app_private.threads WHERE thread_id LIKE %s", (pattern,)
            ).fetchone()[0],
            "tasks": connection.execute(
                "SELECT count(*) FROM app_private.tasks WHERE source_email_id LIKE %s OR thread_id LIKE %s",
                (pattern, pattern),
            ).fetchone()[0],
            "groups": connection.execute(
                "SELECT count(*) FROM app_private.ingest_groups WHERE client_batch_id=%s", (batch_id,)
            ).fetchone()[0],
            "chat": connection.execute(
                "SELECT count(*) FROM app_private.chat_audit WHERE scope_id=%s", (batch_id,)
            ).fetchone()[0],
        }
    assert all(value == 0 for value in remaining.values()), f"production cleanup incomplete: {remaining}"
    deleted["cleanup_verified"] = 1
    return deleted


def main() -> None:
    marker = "api-matrix-" + uuid4().hex
    batch_id = str(uuid4())
    checks: list[str] = []
    direct_task_ids: list[str] = []
    try:
        with httpx.Client(base_url=BASE_URL, timeout=900) as client:
            health = assert_status(client.get("/health"), 200, "health")
            assert health["status"] == "alive"
            ready = assert_status(client.get("/ready"), 200, "ready")
            assert ready["status"] == "ready" and all(
                value in {"ok", "local_persistent", "configured"}
                for value in ready["components"].values()
            )
            config = assert_status(client.get("/api/config"), 200, "config")
            assert config == {
                "app_name": "Alumnx AI Sales inbox task router",
                "candidate_id": CANDIDATE_ID,
                "max_ingest_emails": 100,
            }
            users = assert_status(client.get("/users"), 200, "users")
            assert len(users["team"]) == 6
            checks.append("health_ready_config_users")

            payload = {
                "candidate_id": CANDIDATE_ID,
                "source_email_id": f"{marker}-direct-email",
                "thread_id": f"{marker}-direct-thread",
                "title": "Direct Task API contract",
                "description": "API conformance record",
                "assignee_id": "u_aarti",
                "category": "enterprise_rfp",
                "priority": "medium",
                "due_date": None,
                "deal_value_inr": 2_500_000,
                "company_name": "Contract Test Ltd",
                "confidence": 0.91,
            }
            first = assert_status(client.post("/tasks", json=payload), 201, "task create 1")
            second = assert_status(client.post("/tasks", json=payload), 201, "task create 2")
            direct_task_ids.extend((first["task_id"], second["task_id"]))
            assert first["task_id"] != second["task_id"]
            listed = assert_status(
                client.get(
                    "/tasks",
                    params={"candidate_id": CANDIDATE_ID, "source_email_id": payload["source_email_id"]},
                ),
                200,
                "task list",
            )
            assert len(listed) == 2
            patched = assert_status(
                client.patch(f"/tasks/{first['task_id']}", json={"priority": "high", "due_date": None}),
                200,
                "task patch",
            )
            assert patched["priority"] == "high" and patched["due_date"] is None
            invalid_enum = assert_status(
                client.post("/tasks", json=payload | {"assignee_id": "Aarti"}),
                400,
                "task enum",
            )
            assert invalid_enum == {
                "error": "invalid_enum_value",
                "field": "assignee_id",
                "received": "Aarti",
                "allowed": ["u_aarti", "u_rohit", "u_meera", "u_karan", "u_divya", "u_triage"],
            }
            assert_status(client.patch(f"/tasks/{first['task_id']}", json={}), 400, "empty patch")
            assert_status(client.patch(f"/tasks/{first['task_id']}", json={"priority": None}), 400, "null required")
            assert_status(client.patch("/tasks/not-found", json={"priority": "low"}), 404, "missing patch")
            assert_status(
                client.get("/tasks", params={"candidate_id": "wrong@example.com"}),
                400,
                "wrong task candidate",
            )
            for task_id in direct_task_ids:
                assert_status(client.delete(f"/tasks/{task_id}"), 204, "task delete")
            assert_status(client.delete(f"/tasks/{direct_task_ids[0]}"), 404, "task delete repeat")
            checks.append("task_api_crud_filters_exact_enum_and_no_dedup")

            initial = email(marker, "rfp")
            ooo = email(
                marker,
                "ooo",
                from_name="Automatic reply",
                subject="Out of Office",
                body="Automatic reply: I am out of office until 14 August with limited email access.",
            )
            base_ingest = {
                "candidate_id": CANDIDATE_ID,
                "client_batch_id": batch_id,
                "source": "grader",
            }
            first_ingest = assert_status(
                client.post("/ingest", json=base_ingest | {"emails": [initial, ooo]}),
                200,
                "initial ingest",
            )
            assert first_ingest["processed"] == 2
            assert first_ingest["tasks_created"] == 1 and first_ingest["skipped"] == 1

            reply = email(
                marker,
                "rfp-reply",
                thread_id=initial["thread_id"],
                message_index=1,
                subject="Re: RFP - Enterprise DMS for Meridian Steel",
                body=(
                    "Correction: budget is now Rs. 32 lakhs and the submission deadline is advanced "
                    "to 11th August 2026.\n\nOn the earlier message wrote:\n> Rs. 25 lakhs, due 12th August."
                ),
                received_at="2026-08-09T09:00:00+05:30",
                is_reply=True,
            )
            reply_ingest = assert_status(
                client.post("/ingest", json=base_ingest | {"emails": [reply]}),
                200,
                "reply ingest",
            )
            assert reply_ingest["tasks_updated"] == 1 and reply_ingest["tasks_created"] == 0
            replay = assert_status(
                client.post("/ingest", json=base_ingest | {"emails": [initial]}),
                200,
                "replay",
            )
            assert replay["unchanged"] == 1 and replay["tasks_created"] == 0

            decisions = assert_status(
                client.get(f"/api/batches/{batch_id}/decisions"), 200, "batch decisions"
            )
            assert decisions["total"] == 3
            app_tasks = assert_status(
                client.get("/api/tasks", params={"batch_id": batch_id}), 200, "app tasks"
            )
            assert app_tasks["total"] == 1
            task = app_tasks["items"][0]["task"]
            assert task["source_email_id"] == initial["email_id"]
            assert task["deal_value_inr"] == 3_200_000 and task["due_date"] == "2026-08-11"
            assert app_tasks["items"][0]["decision"]["update_count"] == 1
            assert_status(
                client.get("/api/tasks", params={"batch_id": batch_id, "category": "bad"}),
                400,
                "bad app category",
            )
            assert_status(
                client.get(
                    "/api/tasks",
                    params={"batch_id": batch_id, "confidence_gte": 0.9, "confidence_lte": 0.2},
                ),
                400,
                "bad confidence range",
            )
            stats = assert_status(
                client.get("/api/stats", params={"scope_type": "batch", "scope_id": batch_id}),
                200,
                "batch stats",
            )
            assert stats["unique_processed"] == 3 and stats["delivery_attempts"] == 4
            assert stats["created"] == 1 and stats["updated"] == 1 and stats["skipped"] == 1
            assert stats["current_tasks"] == 1 and stats["update_event_total"] == 1
            checks.append("ingest_create_skip_reply_patch_replay_tasks_decisions_stats")

            feedback = assert_status(
                client.post(
                    f"/api/decisions/{initial['email_id']}/feedback",
                    json={"label": "spurious", "note": "matrix verification"},
                ),
                200,
                "feedback",
            )
            assert feedback["label"] == "spurious"
            flagged_stats = assert_status(
                client.get("/api/stats", params={"scope_type": "batch", "scope_id": batch_id}),
                200,
                "feedback stats",
            )
            assert flagged_stats["confirmed_spurious_count"] == 1
            assert_status(
                client.post("/api/decisions/does-not-exist/feedback", json={"label": "correct"}),
                404,
                "unknown feedback",
            )
            assert_status(
                client.post(
                    f"/api/decisions/{initial['email_id']}/feedback", json={"label": "correct"}
                ),
                200,
                "feedback correction",
            )
            checks.append("feedback_and_confirmed_spurious_semantics")

            questions = (
                "How many proposal or RFP emails came in?",
                "How many were marketing versus actual spam we correctly ignored?",
                "Show me everything sitting in triage and why.",
                "What's our spurious rate so far?",
                "Which tasks are high priority but low confidence?",
                "Break down alliances by subtype.",
                "How many GST refund requests were there?",
                "Send an email to all RFP prospects.",
                "What's the total deal value of all open RFPs?",
                "Which threads were updated more than once?",
            )
            answers = []
            for question in questions:
                response = assert_status(
                    client.post(
                        "/api/chat",
                        json={
                            "candidate_id": CANDIDATE_ID,
                            "query": question,
                            "scope": {"type": "batch", "id": batch_id},
                        },
                    ),
                    200,
                    f"chat: {question}",
                )
                assert response["answer"] and isinstance(response["supporting_data"], dict)
                answers.append(response)
            assert answers[6]["supporting_data"]["count"] == 0
            assert "0" in answers[6]["answer"] or "zero" in answers[6]["answer"].lower()
            assert "can't" in answers[7]["answer"].lower() or "cannot" in answers[7]["answer"].lower()
            repeated = assert_status(
                client.post(
                    "/api/chat",
                    json={
                        "candidate_id": CANDIDATE_ID,
                        "query": questions[0],
                        "scope": {"type": "batch", "id": batch_id},
                    },
                ),
                200,
                "repeated chat",
            )
            assert repeated["supporting_data"] == answers[0]["supporting_data"]
            checks.append("ten_grounded_chat_queries_zero_refusal_and_stability")

            sample = assert_status(client.get("/api/sample-emails", params={"count": 250}), 200, "samples")
            assert len(sample["emails"]) == 250
            forbidden = {"label", "expected_task", "expected_patch", "operation", "confidence"}
            assert not forbidden.intersection(sample["emails"][0])
            assert_status(client.get("/api/sample-emails", params={"count": 0}), 400, "sample lower")
            assert_status(client.get("/api/sample-emails", params={"count": 251}), 400, "sample upper")
            checks.append("sample_contract_without_labels")

            wrong = assert_status(
                client.post("/ingest", json={"candidate_id": "wrong@example.com", "emails": [initial]}),
                400,
                "wrong ingest candidate",
            )
            assert wrong["error"]["code"] == "candidate_id_mismatch"
            assert_status(client.post("/ingest", json={"candidate_id": CANDIDATE_ID, "emails": []}), 400, "empty")
            assert_status(
                client.post(
                    "/ingest",
                    json={"candidate_id": CANDIDATE_ID, "emails": [initial, initial]},
                ),
                400,
                "duplicate email request",
            )
            invalid_email = initial | {"email_id": f"{marker}-invalid-email", "from_email": "not-an-email"}
            assert_status(
                client.post("/ingest", json={"candidate_id": CANDIDATE_ID, "emails": [invalid_email]}),
                400,
                "invalid email",
            )
            naive_time = initial | {"email_id": f"{marker}-naive", "received_at": "2026-08-01T09:00:00"}
            assert_status(
                client.post("/ingest", json={"candidate_id": CANDIDATE_ID, "emails": [naive_time]}),
                400,
                "naive timestamp",
            )
            strict_bool = initial | {"email_id": f"{marker}-bool", "is_reply": "false"}
            assert_status(
                client.post("/ingest", json={"candidate_id": CANDIDATE_ID, "emails": [strict_bool]}),
                400,
                "strict bool",
            )
            conflict = initial | {"body": initial["body"] + " changed"}
            assert_status(
                client.post("/ingest", json=base_ingest | {"emails": [conflict]}),
                409,
                "email content conflict",
            )
            index_conflict = initial | {"email_id": f"{marker}-email-index-conflict"}
            assert_status(
                client.post("/ingest", json=base_ingest | {"emails": [index_conflict]}),
                409,
                "thread index conflict",
            )
            orphan = email(marker, "orphan", message_index=1, is_reply=True)
            assert_status(
                client.post("/ingest", json=base_ingest | {"emails": [orphan]}),
                409,
                "orphan reply",
            )
            malformed = assert_status(
                client.post("/ingest", content="{", headers={"Content-Type": "application/json"}),
                400,
                "malformed json",
            )
            assert malformed["error"]["code"] == "invalid_request"
            assert_status(
                client.post(
                    "/ingest",
                    content=b"x" * 26_214_401,
                    headers={"Content-Type": "application/octet-stream"},
                ),
                413,
                "request too large",
            )
            assert_status(client.get("/api/stats", params={"scope_type": "batch"}), 400, "missing scope")
            assert_status(client.get("/api/batches/not-a-uuid/decisions"), 400, "invalid batch UUID")
            assert_status(client.post("/api/chat", json={"candidate_id": CANDIDATE_ID, "query": ""}), 400, "blank chat")
            assert_status(client.get("/does-not-exist"), 404, "unknown path")
            assert_status(client.put("/tasks/not-found", json={}), 405, "wrong method")
            checks.append("identity_validation_conflicts_limits_orphan_404_405")

            cors = client.options(
                "/api/config",
                headers={
                    "Origin": "http://localhost:5173",
                    "Access-Control-Request-Method": "GET",
                },
            )
            assert cors.status_code == 200
            assert cors.headers.get("access-control-allow-origin") == "http://localhost:5173"
            foreign_cors = client.options(
                "/api/config",
                headers={
                    "Origin": "https://evil.example",
                    "Access-Control-Request-Method": "GET",
                },
            )
            assert foreign_cors.headers.get("access-control-allow-origin") is None
            checks.append("exact_cors_origin")
    finally:
        deleted = cleanup(marker, batch_id)

    report = {
        "base_url": BASE_URL,
        "candidate_id": CANDIDATE_ID,
        "checks_passed": checks,
        "check_group_count": len(checks),
        "cleanup": deleted,
    }
    target = ROOT / "artifacts" / "production_api_matrix.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
