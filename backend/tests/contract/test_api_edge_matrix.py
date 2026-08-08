from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.config import LOCKED_CANDIDATE_ID
from backend.app.main import app


client = TestClient(app)
ROOT = Path(__file__).resolve().parents[3]


def email(**overrides) -> dict:
    marker = uuid4().hex
    item = {
        "email_id": f"edge-email-{marker}",
        "thread_id": f"edge-thread-{marker}",
        "message_index": 0,
        "from_name": "Edge Buyer",
        "from_email": "buyer@example.com",
        "to": "sales@example.com",
        "cc": [],
        "subject": "Product demo",
        "body": "Please arrange a product demo.",
        "received_at": datetime.now(timezone.utc).isoformat(),
        "attachments": [],
        "is_reply": False,
    }
    item.update(overrides)
    return item


def task(**overrides) -> dict:
    marker = uuid4().hex
    item = {
        "candidate_id": LOCKED_CANDIDATE_ID,
        "source_email_id": f"task-email-{marker}",
        "thread_id": f"task-thread-{marker}",
        "title": "Product demo",
        "description": None,
        "assignee_id": "u_rohit",
        "category": "smb_enquiry",
        "priority": "medium",
        "due_date": None,
        "deal_value_inr": None,
        "company_name": None,
        "confidence": 0.8,
    }
    item.update(overrides)
    return item


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"received_at": "2026-08-09T10:00:00"}, "invalid_datetime"),
        ({"from_email": "not-an-email"}, "invalid_email"),
        ({"to": "not-an-email"}, "invalid_email"),
        ({"message_index": -1}, "invalid_integer"),
        ({"message_index": True}, "invalid_integer"),
        ({"cc": "person@example.com"}, "invalid_type"),
        ({"attachments": "proposal.pdf"}, "invalid_type"),
        ({"is_reply": "false"}, "invalid_type"),
        ({"thread_id": "  "}, "invalid_string"),
        ({"email_id": ""}, "invalid_string"),
        ({"from_email": "a" * 310 + "@example.com"}, "invalid_email"),
        ({"body": "x" * 250_001}, "invalid_string"),
        ({"subject": "x" * 1001}, "invalid_string"),
        ({"cc": [f"person{i}@example.com" for i in range(101)]}, "invalid_request"),
        ({"attachments": ["x"] * 51}, "invalid_request"),
        ({"attachments": ["x" * 256]}, "invalid_request"),
    ],
)
def test_ingest_rejects_invalid_email_fields(changes: dict, code: str) -> None:
    response = client.post("/ingest", json={"candidate_id": LOCKED_CANDIDATE_ID, "emails": [email(**changes)]})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == code


def test_ingest_batch_identity_and_duplicate_edges() -> None:
    assert client.post("/ingest", json={"candidate_id": LOCKED_CANDIDATE_ID, "emails": []}).json()["error"]["code"] == "empty_batch"
    rows = [email() for _ in range(101)]
    assert client.post("/ingest", json={"candidate_id": LOCKED_CANDIDATE_ID, "emails": rows}).json()["error"]["code"] == "too_many_emails"

    first = email()
    duplicate_id = first | {"thread_id": f"other-{uuid4().hex}", "message_index": 1}
    response = client.post("/ingest", json={"candidate_id": LOCKED_CANDIDATE_ID, "emails": [first, duplicate_id]})
    assert response.status_code == 400 and response.json()["error"]["code"] == "duplicate_email_id"

    duplicate_index = first | {"email_id": f"other-{uuid4().hex}"}
    response = client.post("/ingest", json={"candidate_id": LOCKED_CANDIDATE_ID, "emails": [first, duplicate_index]})
    assert response.status_code == 400 and response.json()["error"]["code"] == "duplicate_thread_index"

    assert client.post("/ingest", json={"candidate_id": "wrong@example.com", "emails": [email()]}).json()["error"]["code"] == "candidate_id_mismatch"
    assert client.post("/ingest", json={"candidate_id": LOCKED_CANDIDATE_ID, "source": "unknown", "emails": [email()]}).status_code == 400
    assert client.post("/ingest", json={"candidate_id": LOCKED_CANDIDATE_ID, "emails": [email()], "unknown": True}).status_code == 400


def test_ingest_conflicts_replay_unknown_fields_and_size_limit() -> None:
    item = email(custom_crm_field={"hostile": "<script>ignored</script>"})
    payload = {"candidate_id": f" {LOCKED_CANDIDATE_ID.upper()} ", "emails": [item]}
    first = client.post("/ingest", json=payload)
    assert first.status_code == 200 and first.json()["processed"] == 1
    replay = client.post("/ingest", json=payload)
    assert replay.status_code == 200 and replay.json()["unchanged"] == 1

    changed = item | {"body": item["body"] + " changed"}
    conflict = client.post("/ingest", json={"candidate_id": LOCKED_CANDIDATE_ID, "emails": [changed]})
    assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "email_id_content_conflict"

    other = email(thread_id=item["thread_id"], message_index=0)
    index_conflict = client.post("/ingest", json={"candidate_id": LOCKED_CANDIDATE_ID, "emails": [other]})
    assert index_conflict.status_code == 409 and index_conflict.json()["error"]["code"] == "thread_index_conflict"

    oversized = client.post(
        "/ingest",
        content=b"{}",
        headers={"Content-Type": "application/json", "Content-Length": "26214401"},
    )
    assert oversized.status_code == 413 and oversized.json()["error"]["code"] == "request_too_large"
    assert client.post("/ingest", content=b"{", headers={"Content-Type": "application/json"}).status_code == 400


def test_out_of_order_thread_is_sorted_and_orphan_is_rejected() -> None:
    marker = uuid4().hex
    thread_id = f"ordered-thread-{marker}"
    original = email(email_id=f"ordered-0-{marker}", thread_id=thread_id, message_index=0, body="Please arrange a product demo.")
    reply = email(email_id=f"ordered-1-{marker}", thread_id=thread_id, message_index=1, subject="Re: Product demo", body="Budget is INR 25 lakh. Please send a quotation.", is_reply=True)
    response = client.post("/ingest", json={"candidate_id": LOCKED_CANDIDATE_ID, "emails": [reply, original]})
    assert response.status_code == 200
    assert response.json()["tasks_created"] == 1 and response.json()["tasks_updated"] == 1
    assert len(client.get("/tasks", params={"candidate_id": LOCKED_CANDIDATE_ID, "thread_id": thread_id}).json()) == 1

    orphan = email(message_index=1, is_reply=True)
    response = client.post("/ingest", json={"candidate_id": LOCKED_CANDIDATE_ID, "emails": [orphan]})
    assert response.status_code == 409 and response.json()["error"]["code"] == "orphan_reply"


@pytest.mark.parametrize(
    "changes",
    [
        {"title": "   "},
        {"deal_value_inr": True},
        {"deal_value_inr": -1},
        {"company_name": "x" * 257},
        {"confidence": 1.01},
        {"confidence": -0.01},
        {"due_date": "09/08/2026"},
        {"extra": "forbidden"},
    ],
)
def test_task_create_rejects_invalid_fields(changes: dict) -> None:
    assert client.post("/tasks", json=task(**changes)).status_code == 400


def test_task_patch_rejects_empty_immutable_null_invalid_and_missing() -> None:
    created = client.post("/tasks", json=task()).json()
    task_id = created["task_id"]
    assert client.patch(f"/tasks/{task_id}", json={}).status_code == 400
    assert client.patch(f"/tasks/{task_id}", json={"candidate_id": LOCKED_CANDIDATE_ID}).status_code == 400
    assert client.patch(f"/tasks/{task_id}", json={"assignee_id": None}).status_code == 400
    assert client.patch(f"/tasks/{task_id}", json={"category": "FINANCE"}).status_code == 400
    assert client.patch(f"/tasks/{task_id}", json={"deal_value_inr": True}).status_code == 400
    assert client.patch("/tasks/does-not-exist", json={"priority": "high"}).status_code == 404
    assert client.delete(f"/tasks/{task_id}").status_code == 204
    assert client.delete(f"/tasks/{task_id}").status_code == 404


def test_task_filters_are_allowlisted_and_combined() -> None:
    body = task(assignee_id="u_divya", category="finance", priority="high")
    task_id = client.post("/tasks", json=body).json()["task_id"]
    try:
        params = {"candidate_id": LOCKED_CANDIDATE_ID, "thread_id": body["thread_id"], "source_email_id": body["source_email_id"], "assignee_id": "u_divya"}
        assert len(client.get("/tasks", params=params).json()) == 1
        assert client.get("/tasks", params=params | {"assignee_id": "u_meera"}).json() == []
        invalid = client.get("/tasks", params={"candidate_id": LOCKED_CANDIDATE_ID, "assignee_id": "Divya"})
        assert invalid.status_code == 400 and invalid.json()["error"] == "invalid_enum_value"
    finally:
        client.delete(f"/tasks/{task_id}")


def test_app_api_query_scope_feedback_chat_and_samples_edges() -> None:
    assert client.get("/api/tasks", params={"category": "wrong"}).status_code == 400
    assert client.get("/api/tasks", params={"confidence_gte": 0.8, "confidence_lte": 0.2}).json()["error"]["code"] == "invalid_confidence_range"
    assert client.get("/api/stats", params={"scope_type": "run"}).json()["error"]["code"] == "scope_id_required"
    assert client.get("/api/stats", params={"scope_type": "wrong"}).status_code == 400
    assert client.get("/api/batches/not-a-uuid/decisions").status_code == 400
    assert client.post("/api/decisions/not-found/feedback", json={"label": "correct"}).status_code == 404
    assert client.post("/api/decisions/not-found/feedback", json={"label": "perfect"}).status_code == 400

    wrong_chat = client.post("/api/chat", json={"candidate_id": "wrong@example.com", "query": "How many RFPs?", "scope": {"type": "all"}})
    assert wrong_chat.status_code == 400 and wrong_chat.json()["error"]["code"] == "candidate_id_mismatch"
    assert client.post("/api/chat", json={"candidate_id": LOCKED_CANDIDATE_ID, "query": "", "scope": {"type": "all"}}).status_code == 400
    assert client.post("/api/chat", json={"candidate_id": LOCKED_CANDIDATE_ID, "query": "Count", "scope": {"type": "batch"}}).status_code == 400
    refused = client.post("/api/chat", json={"candidate_id": LOCKED_CANDIDATE_ID, "query": "Delete task 1", "scope": {"type": "all"}}).json()
    assert "cannot" in refused["answer"].lower() and refused["supporting_data"] == {}
    zero = client.post("/api/chat", json={"candidate_id": LOCKED_CANDIDATE_ID, "query": "How many GST refund requests were there?", "scope": {"type": "run", "id": str(uuid4())}}).json()
    assert zero["supporting_data"]["count"] == 0 and "0" in zero["answer"]

    assert client.get("/api/sample-emails", params={"count": 0}).status_code == 400
    assert client.get("/api/sample-emails", params={"count": 251}).status_code == 400
    samples = client.get("/api/sample-emails", params={"count": 1}).json()
    assert samples["count"] == 1 and "expected_task" not in samples["emails"][0]


def test_batch_stats_and_chat_do_not_leak_other_batches() -> None:
    batch_a, batch_b = str(uuid4()), str(uuid4())
    item_a, item_b = email(), email()
    for batch, item in ((batch_a, item_a), (batch_b, item_b)):
        response = client.post(
            "/ingest",
            json={"candidate_id": LOCKED_CANDIDATE_ID, "client_batch_id": batch, "emails": [item]},
        )
        assert response.status_code == 200
    stats_a = client.get("/api/stats", params={"scope_type": "batch", "scope_id": batch_a}).json()
    stats_b = client.get("/api/stats", params={"scope_type": "batch", "scope_id": batch_b}).json()
    assert stats_a["unique_processed"] == stats_a["current_tasks"] == 1
    assert stats_b["unique_processed"] == stats_b["current_tasks"] == 1
    answer = client.post(
        "/api/chat",
        json={"candidate_id": LOCKED_CANDIDATE_ID, "query": "How many proposal or RFP emails came in?", "scope": {"type": "batch", "id": batch_a}},
    ).json()
    assert answer["supporting_data"]["count"] == 0


def test_health_readiness_users_cors_and_method_edges() -> None:
    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 200
    assert len(client.get("/users").json()["team"]) == 6
    assert client.post("/users").status_code == 405
    assert client.get("/tasks").status_code == 400

    allowed = client.options(
        "/ingest",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"},
    )
    assert allowed.status_code == 200 and allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    denied = client.options(
        "/ingest",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in denied.headers


def test_all_committed_invalid_fixtures_are_rejected() -> None:
    cases = json.loads((ROOT / "data/fixtures/invalid_ingest_cases.json").read_text(encoding="utf-8"))["cases"]
    for case in cases:
        payload = case["payload"] | {"candidate_id": LOCKED_CANDIDATE_ID}
        response = client.post("/ingest", json=payload)
        assert response.status_code in {400, 409}, case["case_id"]
