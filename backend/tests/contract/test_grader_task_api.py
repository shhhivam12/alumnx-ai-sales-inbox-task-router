from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app.config import LOCKED_CANDIDATE_ID
from backend.app.main import app


client = TestClient(app)


def payload() -> dict:
    marker = uuid4().hex
    return {
        "candidate_id": LOCKED_CANDIDATE_ID,
        "source_email_id": f"email-{marker}",
        "thread_id": f"thread-{marker}",
        "title": "Demo request",
        "description": "Buyer requested a demo.",
        "assignee_id": "u_rohit",
        "category": "smb_enquiry",
        "priority": "medium",
        "due_date": None,
        "deal_value_inr": None,
        "company_name": None,
        "confidence": 0.84,
    }


def test_exact_create_list_patch_delete_contract() -> None:
    body = payload()
    created = client.post("/tasks", json=body)
    assert created.status_code == 201
    assert set(created.json()) == {"task_id", "candidate_id", "source_email_id", "created_at"}
    task_id = created.json()["task_id"]

    listed = client.get("/tasks", params={"candidate_id": LOCKED_CANDIDATE_ID, "thread_id": body["thread_id"]})
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0] | {"created_at": None} == (
        body | {"task_id": task_id, "created_at": None}
    )

    updated = client.patch(f"/tasks/{task_id}", json={"priority": "high", "deal_value_inr": 1_000_001})
    assert updated.status_code == 200
    assert updated.json()["priority"] == "high"
    assert updated.json()["deal_value_inr"] == 1_000_001
    assert updated.json()["candidate_id"] == LOCKED_CANDIDATE_ID

    deleted = client.delete(f"/tasks/{task_id}")
    assert deleted.status_code == 204
    assert client.get("/tasks", params={"candidate_id": LOCKED_CANDIDATE_ID, "thread_id": body["thread_id"]}).json() == []


def test_direct_post_deliberately_does_not_deduplicate() -> None:
    body = payload()
    first = client.post("/tasks", json=body)
    second = client.post("/tasks", json=body)
    assert first.status_code == second.status_code == 201
    assert first.json()["task_id"] != second.json()["task_id"]
    tasks = client.get("/tasks", params={"candidate_id": LOCKED_CANDIDATE_ID, "source_email_id": body["source_email_id"]}).json()
    assert len(tasks) == 2
    for task in tasks:
        assert client.delete(f"/tasks/{task['task_id']}").status_code == 204


def test_candidate_and_enum_validation_match_grader_contract() -> None:
    wrong = payload() | {"candidate_id": "someone@example.com"}
    response = client.post("/tasks", json=wrong)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "candidate_id_mismatch"

    invalid = payload() | {"assignee_id": "Aarti"}
    response = client.post("/tasks", json=invalid)
    assert response.status_code == 400
    assert response.json() == {
        "error": "invalid_enum_value",
        "field": "assignee_id",
        "received": "Aarti",
        "allowed": ["u_aarti", "u_rohit", "u_meera", "u_karan", "u_divya", "u_triage"],
    }

    assert client.get("/tasks").status_code == 400
    assert client.get("/tasks", params={"candidate_id": "wrong@example.com"}).status_code == 400


def test_users_returns_the_exact_team_roster() -> None:
    response = client.get("/users")
    assert response.status_code == 200
    assert [user["user_id"] for user in response.json()["team"]] == [
        "u_aarti", "u_rohit", "u_meera", "u_karan", "u_divya", "u_triage"
    ]
