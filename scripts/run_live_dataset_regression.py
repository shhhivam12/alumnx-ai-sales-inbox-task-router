from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from uuid import uuid4

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.config import Settings  # noqa: E402
from backend.app.domain.email_models import IngestRequest  # noqa: E402
from backend.app.repositories.store import MemoryStore  # noqa: E402
from backend.app.services.gemini_extractor import GeminiExtractor  # noqa: E402
from backend.app.services.ingestion_service import IngestionService  # noqa: E402
from backend.app.services.reconciler import Reconciler  # noqa: E402

CANDIDATE_ID = "mahendrushivam123@gmail.com"


def oracle_states(expected: list[dict]) -> dict[str, dict | None]:
    states: dict[str, dict] = {}
    result = {}
    for decision in expected:
        thread_id = decision["thread_id"]
        if decision["operation"] == "create" and decision.get("expected_task"):
            states[thread_id] = dict(decision["expected_task"])
        elif decision["operation"] == "update" and decision.get("expected_patch"):
            states[thread_id].update(decision["expected_patch"])
        result[decision["email_id"]] = dict(states[thread_id]) if thread_id in states else None
    return result


def main() -> None:
    env = dotenv_values(ROOT / ".env")
    key = env.get("GEMINI_API_KEY")
    if not key:
        raise SystemExit("GEMINI_API_KEY is required")
    settings = Settings(
        app_env="test",
        supabase_db_url="", supabase_migration_db_url="",
        gemini_api_key=key, gemini_model=env.get("GEMINI_MODEL") or "gemini-3.5-flash-lite",
        gemini_requests_per_minute=int(env.get("GEMINI_REQUESTS_PER_MINUTE") or 5),
        gemini_max_retries=2,
    )
    emails = json.loads((ROOT / "data/inbox.json").read_text(encoding="utf-8"))
    expected = json.loads((ROOT / "data/ground_truth/expected_decisions.json").read_text(encoding="utf-8"))["decisions"]
    expected_by_id = {item["email_id"]: item for item in expected}
    expected_state = oracle_states(expected)
    store = MemoryStore()
    service = IngestionService(settings, store, GeminiExtractor(settings), Reconciler(store))
    batch_id = uuid4()
    responses = []
    for offset in range(0, len(emails), 100):
        request = IngestRequest(candidate_id=CANDIDATE_ID, client_batch_id=batch_id, source="generated", emails=emails[offset:offset + 100])
        response = service.ingest(request); responses.append(response.model_dump(mode="json"))
        print(f"Completed {min(offset + 100, len(emails))}/{len(emails)} emails")

    actual = {item["email_id"]: item for item in store.list_decisions("batch", str(batch_id))}
    operation_correct = 0; route_correct = 0; route_total = 0; field_correct = Counter(); field_total = Counter()
    mismatches = []
    predictions = []
    for email_id, expected_decision in expected_by_id.items():
        item = actual.get(email_id)
        if not item:
            mismatches.append({"email_id": email_id, "field": "missing_decision"}); continue
        task = item.get("task")
        predictions.append({
            "email_id": email_id,
            "operation": item["operation"],
            "assignee_id": (task or {}).get("assignee_id"),
            "category": (task or {}).get("category"),
            "priority": (task or {}).get("priority"),
            "due_date": (task or {}).get("due_date"),
            "deal_value_inr": (task or {}).get("deal_value_inr"),
            "company_name": (task or {}).get("company_name"),
            "confidence": item.get("confidence"),
        })
        if item["operation"] == expected_decision["operation"]:
            operation_correct += 1
        else:
            mismatches.append({"email_id": email_id, "field": "operation", "expected": expected_decision["operation"], "actual": item["operation"]})
        oracle = expected_state[email_id]
        if oracle and task and item["operation"] not in {"skip", "noop"}:
            route_total += 1
            if task.get("assignee_id") == oracle.get("assignee_id") and task.get("category") == oracle.get("category"):
                route_correct += 1
            else:
                mismatches.append({
                    "email_id": email_id,
                    "field": "owner_category",
                    "expected": [oracle.get("assignee_id"), oracle.get("category")],
                    "actual": [task.get("assignee_id"), task.get("category")],
                })
            for field in ("priority", "due_date", "deal_value_inr", "company_name"):
                field_total[field] += 1
                if task.get(field) == oracle.get(field):
                    field_correct[field] += 1
                else:
                    mismatches.append({
                        "email_id": email_id,
                        "field": field,
                        "expected": oracle.get(field),
                        "actual": task.get(field),
                    })
        elif bool(oracle) != bool(task) and item["operation"] not in {"skip", "noop"}:
            mismatches.append({
                "email_id": email_id,
                "field": "task_presence",
                "expected": bool(oracle),
                "actual": bool(task),
            })
    summary = {
        "warning": "Synthetic ground-truth regression only; not a substitute for personally reviewed eval_60 labels.",
        "model": settings.gemini_model,
        "emails": len(expected),
        "responses": responses,
        "operation_accuracy": round(operation_correct / len(expected), 4),
        "owner_category_accuracy": round(route_correct / route_total, 4) if route_total else 0,
        "field_exact_match": {field: round(field_correct[field] / total, 4) for field, total in field_total.items()},
        "actual_operations": dict(Counter(item["operation"] for item in actual.values())),
        "degraded_count": sum(bool(item.get("degraded_mode")) for item in actual.values()),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "predictions": predictions,
    }
    target = ROOT / "artifacts/live_dataset_regression.json"
    target.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key not in {"responses", "mismatches", "predictions"}}, indent=2))
    print(target)


if __name__ == "__main__":
    main()
