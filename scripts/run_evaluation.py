from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("oracle", "reviewed"), default="oracle")
    parser.add_argument("--predictions", default="artifacts/live_eval_predictions.json")
    args = parser.parse_args()
    if args.mode == "oracle":
        subprocess.run([sys.executable, str(ROOT / "scripts/validate_dataset.py")], cwd=ROOT, check=True)
        print("Oracle corpus integrity passed; expected lifecycle remains frozen in data/ground_truth.")
        return
    labels_path = ROOT / "artifacts/manual_eval_blind.json"
    predictions_path = ROOT / args.predictions
    if not labels_path.exists() or not predictions_path.exists():
        raise SystemExit("Reviewed labels and live predictions are required; draft synthetic labels are never substituted.")
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    predictions = json.loads(predictions_path.read_text(encoding="utf-8"))
    expected = {item["email"]["email_id"]: item["human_label"] for item in labels}
    actual = {item["email_id"]: item for item in predictions}
    missing = sorted(set(expected) - set(actual))
    if missing:
        raise SystemExit(f"Predictions missing {len(missing)} reviewed email IDs")
    fields = ("operation", "assignee_id", "category", "priority", "due_date", "deal_value_inr", "company_name")
    report = {}
    for field in fields:
        correct = sum(expected[email_id].get(field) == actual[email_id].get(field) for email_id in expected)
        report[field + "_exact_match"] = correct / len(expected) if expected else 0
    report["expected_categories"] = dict(Counter(item.get("category") for item in expected.values()))
    target = ROOT / "artifacts/evaluation_report.json"
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(target)


if __name__ == "__main__":
    main()
