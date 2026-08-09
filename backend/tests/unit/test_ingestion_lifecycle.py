from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app.main import app


def message(email_id: str, thread_id: str, index: int, body: str, *, reply: bool = False) -> dict:
    return {
        "email_id": email_id,
        "thread_id": thread_id,
        "message_index": index,
        "from_name": "Buyer",
        "from_email": "buyer@example.com",
        "to": "sales@example.com",
        "cc": [],
        "subject": "Re: Product licences" if reply else "Product licences",
        "body": body,
        "received_at": (datetime(2026, 8, 8, 10, tzinfo=timezone.utc) + timedelta(hours=index)).isoformat(),
        "attachments": [],
        "is_reply": reply,
    }


def test_replay_is_unchanged_and_reply_patches_one_task() -> None:
    client = TestClient(app)
    suffix = uuid4().hex[:8]
    thread_id = f"thread-{suffix}"
    first = message(f"email-{suffix}-0", thread_id, 0, "Please arrange a product demo and pricing.")
    payload = {"candidate_id": " MAHENDRUSHIVAM123@GMAIL.COM ", "emails": [first]}
    created = client.post("/ingest", json=payload)
    assert created.status_code == 200
    assert created.json()["tasks_created"] == 1

    replay = client.post("/ingest", json=payload)
    assert replay.status_code == 200
    assert replay.json()["unchanged"] == 1
    assert replay.json()["tasks_created"] == 0

    reply = message(f"email-{suffix}-1", thread_id, 1, "Budget approved at INR 25 lakh. Please send the quotation.", reply=True)
    updated = client.post("/ingest", json={"candidate_id": "mahendrushivam123@gmail.com", "emails": [reply]})
    assert updated.status_code == 200
    assert updated.json()["tasks_updated"] == 1
    tasks = client.get("/api/tasks", params={"thread_id": thread_id}).json()["items"]
    assert len(tasks) == 1
    assert tasks[0]["task"]["category"] == "enterprise_rfp"
    assert tasks[0]["task"]["source_email_id"] == first["email_id"]


def test_replay_in_a_new_batch_retains_the_original_decision_for_audit() -> None:
    client = TestClient(app)
    suffix = uuid4().hex[:8]
    first_batch, replay_batch = str(uuid4()), str(uuid4())
    item = message(f"delivery-email-{suffix}", f"delivery-thread-{suffix}", 0, "Please arrange a product demo and pricing.")

    created = client.post(
        "/ingest",
        json={"candidate_id": "mahendrushivam123@gmail.com", "client_batch_id": first_batch, "emails": [item]},
    )
    assert created.status_code == 200 and created.json()["tasks_created"] == 1

    replayed = client.post(
        "/ingest",
        json={"candidate_id": "mahendrushivam123@gmail.com", "client_batch_id": replay_batch, "emails": [item]},
    )
    assert replayed.status_code == 200 and replayed.json()["unchanged"] == 1
    replayed_again = client.post(
        "/ingest",
        json={"candidate_id": "mahendrushivam123@gmail.com", "client_batch_id": replay_batch, "emails": [item]},
    )
    assert replayed_again.status_code == 200 and replayed_again.json()["unchanged"] == 1

    decisions = client.get(f"/api/batches/{replay_batch}/decisions").json()["items"]
    assert len(decisions) == 1
    assert decisions[0]["email_id"] == item["email_id"]
    assert decisions[0]["operation"] == "create"
    assert decisions[0]["delivery_outcome"] == "unchanged"
    assert decisions[0]["original_operation"] == "create"
    assert decisions[0]["task"]["category"] == "smb_enquiry"

    replay_tasks = client.get("/api/tasks", params={"batch_id": replay_batch}).json()
    assert replay_tasks["total"] == 1
    assert replay_tasks["items"][0]["task"]["source_email_id"] == item["email_id"]
    assert replay_tasks["items"][0]["decision"]["run_id"] == str(replayed_again.json()["run_id"])

    stats = client.get("/api/stats", params={"scope_type": "batch", "scope_id": replay_batch}).json()
    assert stats["unique_processed"] == 1
    assert stats["created"] == 1
    assert stats["delivery_attempts"] == 2
    assert stats["unchanged"] == 2
