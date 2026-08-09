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
CATEGORIES = ("enterprise_rfp", "smb_enquiry", "marketing", "alliances", "finance", "triage")


def ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def main() -> None:
    manual = json.loads((ROOT / "artifacts/manual_eval.json").read_text(encoding="utf-8"))
    items = manual["items"]
    if len(items) != 60 or any(not item["human_label"].get("reviewed") for item in items):
        raise SystemExit("manual_eval.json must contain 60 reviewed labels")

    env = dotenv_values(ROOT / ".env")
    key = env.get("GEMINI_API_KEY")
    if not key:
        raise SystemExit("GEMINI_API_KEY is required")
    settings = Settings(
        app_env="test",
        supabase_db_url="",
        supabase_migration_db_url="",
        gemini_api_key=key,
        gemini_model=env.get("GEMINI_MODEL") or "gemini-3.5-flash-lite",
        gemini_requests_per_minute=int(env.get("GEMINI_REQUESTS_PER_MINUTE") or 5),
        gemini_max_retries=2,
    )
    store = MemoryStore()
    service = IngestionService(settings, store, GeminiExtractor(settings), Reconciler(store))
    batch_id = uuid4()
    request = IngestRequest(
        candidate_id=CANDIDATE_ID,
        client_batch_id=batch_id,
        source="grader",
        emails=[item["email"] for item in items],
    )
    response = service.ingest(request)
    actual = {item["email_id"]: item for item in store.list_decisions("batch", str(batch_id))}

    predictions = []
    mismatches = []
    operation_correct = 0
    field_correct: Counter[str] = Counter()
    field_total: Counter[str] = Counter()
    confusion = {category: Counter() for category in CATEGORIES}
    confidence_rows = []
    skipped_expected = skipped_actual = spurious = missed = 0

    for reviewed in items:
        email_id = reviewed["email"]["email_id"]
        expected = reviewed["human_label"]
        decision = actual.get(email_id)
        if decision is None:
            mismatches.append({"email_id": email_id, "field": "missing_decision"})
            continue
        task = decision.get("task") or {}
        prediction = {
            "email_id": email_id,
            "operation": decision["operation"],
            "assignee_id": task.get("assignee_id"),
            "category": task.get("category"),
            "priority": task.get("priority"),
            "due_date": task.get("due_date"),
            "deal_value_inr": task.get("deal_value_inr"),
            "company_name": task.get("company_name"),
            "confidence": decision.get("confidence"),
            "degraded_mode": decision.get("degraded_mode", False),
        }
        predictions.append(prediction)
        correct = decision["operation"] == expected["operation"]
        if correct:
            operation_correct += 1
        else:
            mismatches.append({"email_id": email_id, "field": "operation", "expected": expected["operation"], "actual": decision["operation"]})

        if expected["operation"] == "skip":
            skipped_expected += 1
            if decision["operation"] == "skip":
                skipped_actual += 1
            elif decision["operation"] in {"create", "update"}:
                spurious += 1
        elif expected["operation"] == "create":
            if decision["operation"] != "create":
                missed += 1
            expected_category = expected["category"]
            actual_category = task.get("category") or "no_task"
            confusion[expected_category][actual_category] += 1
            route_ok = task.get("assignee_id") == expected["assignee_id"] and actual_category == expected_category
            correct = correct and route_ok
            if not route_ok:
                mismatches.append({"email_id": email_id, "field": "owner_category", "expected": [expected["assignee_id"], expected_category], "actual": [task.get("assignee_id"), actual_category]})
            for field in ("priority", "due_date", "deal_value_inr", "company_name"):
                field_total[field] += 1
                if task.get(field) == expected.get(field):
                    field_correct[field] += 1
                else:
                    correct = False
                    mismatches.append({"email_id": email_id, "field": field, "expected": expected.get(field), "actual": task.get(field)})
        confidence_rows.append((float(decision.get("confidence") or 0), correct))

    category_metrics = {}
    for category in CATEGORIES:
        tp = confusion[category][category]
        expected_count = sum(confusion[category].values())
        predicted_count = sum(row[category] for row in confusion.values())
        precision = ratio(tp, predicted_count)
        recall = ratio(tp, expected_count)
        category_metrics[category] = {
            "support": expected_count,
            "precision": precision,
            "recall": recall,
            "f1": ratio(2 * precision * recall, precision + recall),
        }

    bins = ((0.0, 0.6), (0.6, 0.8), (0.8, 1.01))
    calibration = []
    for lower, upper in bins:
        rows = [(confidence, correct) for confidence, correct in confidence_rows if lower <= confidence < upper]
        if rows:
            calibration.append({
                "range": f"{lower:.1f}-{min(upper, 1.0):.1f}",
                "count": len(rows),
                "mean_confidence": round(sum(row[0] for row in rows) / len(rows), 4),
                "accuracy": ratio(sum(row[1] for row in rows), len(rows)),
            })

    report = {
        "evaluation_type": "frozen human-reviewed 60-message set",
        "model": settings.gemini_model,
        "evaluated_at": manual.get("completed_at"),
        "emails": len(items),
        "operations": dict(Counter(item["human_label"]["operation"] for item in items)),
        "operation_accuracy": ratio(operation_correct, len(items)),
        "category_metrics": category_metrics,
        "skip_precision": ratio(skipped_actual, sum(1 for item in predictions if item["operation"] == "skip")),
        "skip_recall": ratio(skipped_actual, skipped_expected),
        "spurious_count": spurious,
        "spurious_rate": ratio(spurious, len(items)),
        "missed_count": missed,
        "create_field_exact_match": {field: ratio(field_correct[field], total) for field, total in field_total.items()},
        "confusion_matrix": {category: dict(row) for category, row in confusion.items()},
        "confidence_calibration": calibration,
        "degraded_count": sum(bool(item["degraded_mode"]) for item in predictions),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "ingest_response": response.model_dump(mode="json"),
    }
    (ROOT / "artifacts/live_eval_predictions.json").write_text(json.dumps(predictions, indent=2, ensure_ascii=False), encoding="utf-8")
    (ROOT / "artifacts/evaluation_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key not in {"mismatches", "confusion_matrix"}}, indent=2))


if __name__ == "__main__":
    main()
