from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_ID = "mahendrushivam123@gmail.com"


def main() -> None:
    base = "http://127.0.0.1:8000"
    emails = json.loads((ROOT / "data/inbox.json").read_text(encoding="utf-8"))
    batch_id = str(uuid4())
    with httpx.Client(base_url=base, timeout=120) as client:
        assert client.get("/health").json()["status"] == "alive"
        assert client.get("/ready").json()["status"] == "ready"
        config = client.get("/api/config").json()
        assert config["candidate_id"] == CANDIDATE_ID
        sample = client.get("/api/sample-emails", params={"count": 250}).json()
        assert len(sample["emails"]) == 250 and "label" not in sample["emails"][0]

        wrong = client.post("/ingest", json={"candidate_id": "wrong@example.com", "emails": emails[:1]})
        assert wrong.status_code == 400 and wrong.json()["error"]["code"] == "candidate_id_mismatch"

        responses = []
        for offset in range(0, 250, 100):
            response = client.post("/ingest", json={"candidate_id": CANDIDATE_ID, "client_batch_id": batch_id, "source": "generated", "emails": emails[offset:offset + 100]})
            response.raise_for_status(); responses.append(response.json())
        assert sum(item["processed"] for item in responses) == 250
        assert sum(len(item["errors"]) for item in responses) == 0

        replay = client.post("/ingest", json={"candidate_id": CANDIDATE_ID, "client_batch_id": batch_id, "source": "generated", "emails": emails[:100]})
        replay.raise_for_status()
        assert replay.json()["processed"] == 100 and replay.json()["unchanged"] == 100 and replay.json()["tasks_created"] == 0

        decisions = client.get(f"/api/batches/{batch_id}/decisions").json()
        assert decisions["total"] == 250
        stats = client.get("/api/stats", params={"scope_type": "batch", "scope_id": batch_id}).json()
        assert stats["unique_processed"] == 250 and stats["delivery_attempts"] == 350
        tasks = client.get("/api/tasks", params={"batch_id": batch_id}).json()
        assert tasks["total"] == stats["current_tasks"]

        first_email = decisions["items"][0]["email_id"]
        feedback = client.post(f"/api/decisions/{first_email}/feedback", json={"label": "correct", "note": "local API smoke"})
        feedback.raise_for_status()

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
        for question in questions:
            answer = client.post("/api/chat", json={"candidate_id": CANDIDATE_ID, "query": question, "scope": {"type": "batch", "id": batch_id}})
            answer.raise_for_status()
            body = answer.json()
            assert body["answer"] and isinstance(body["supporting_data"], dict)
    print("Local API smoke passed: health, readiness, config, samples, 250 ingest, replay, tasks, decisions, stats, feedback, and 10 chat contracts.")


if __name__ == "__main__":
    main()
