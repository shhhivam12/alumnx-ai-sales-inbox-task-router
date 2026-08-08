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
