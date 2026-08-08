"""Validate the generated Sales Inbox Agent dataset without dependencies."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SCHEMA_VERSION = "1.0.0"

EMAIL_FIELDS = {
    "email_id", "thread_id", "message_index", "from_name", "from_email",
    "to", "cc", "subject", "body", "received_at", "attachments", "is_reply",
}
TASK_FIELDS = {
    "source_email_id", "thread_id", "title", "description", "assignee_id",
    "category", "priority", "due_date", "deal_value_inr", "company_name",
    "confidence",
}
MUTABLE_TASK_FIELDS = TASK_FIELDS - {"source_email_id", "thread_id"}
DECISION_FIELDS = {
    "email_id", "thread_id", "message_index", "operation", "skip_reason",
    "expected_task", "expected_patch", "task_key", "rationale", "evidence",
    "confidence_range", "facets",
}
OPERATIONS = {"create", "update", "skip", "noop"}
SKIP_REASONS = {"out_of_office", "newsletter", "vendor_spam", "automated_bounce"}
PRIORITIES = {"low", "medium", "high"}
CATEGORIES = {"enterprise_rfp", "smb_enquiry", "marketing", "alliances", "finance", "triage"}
ASSIGNEE_CATEGORY = {
    "u_aarti": "enterprise_rfp",
    "u_rohit": "smb_enquiry",
    "u_meera": "marketing",
    "u_karan": "alliances",
    "u_divya": "finance",
    "u_triage": "triage",
}
EXPECTED_INITIAL_SCENARIOS = {
    "enterprise": 34, "smb": 30, "marketing": 26, "alliances": 22,
    "finance": 26, "triage": 18, "ooo": 12, "newsletter": 10,
    "spam": 16, "bounce": 6,
}
EXPECTED_OPERATION_COUNTS = {"create": 156, "update": 42, "skip": 49, "noop": 3}
EXPECTED_FINAL_CATEGORIES = {
    "alliances": 21, "enterprise_rfp": 39, "finance": 26,
    "marketing": 27, "smb_enquiry": 27, "triage": 16,
}
EXPECTED_FIXTURES = {
    "missing_email_id": ("missing_required_field", "emails[0].email_id"),
    "empty_thread_id": ("invalid_string", "emails[0].thread_id"),
    "invalid_timestamp": ("invalid_datetime", "emails[0].received_at"),
    "cc_not_array": ("invalid_type", "emails[0].cc"),
    "attachments_not_array": ("invalid_type", "emails[0].attachments"),
    "is_reply_not_boolean": ("invalid_type", "emails[0].is_reply"),
    "negative_message_index": ("invalid_integer", "emails[0].message_index"),
    "invalid_sender_email": ("invalid_email", "emails[0].from_email"),
    "duplicate_email_id_in_request": ("duplicate_email_id", "emails[1].email_id"),
    "orphan_reply_index": ("non_contiguous_message_index", "emails[0].message_index"),
    "batch_over_limit": ("too_many_emails", "emails"),
}
TRACKED_FILES = {
    "data/inbox.json": DATA / "inbox.json",
    "data/team_roster.json": DATA / "team_roster.json",
    "data/ground_truth/expected_decisions.json": DATA / "ground_truth" / "expected_decisions.json",
    "data/ground_truth/expected_tasks.json": DATA / "ground_truth" / "expected_tasks.json",
    "data/eval/eval_60.json": DATA / "eval" / "eval_60.json",
    "data/fixtures/invalid_ingest_cases.json": DATA / "fixtures" / "invalid_ingest_cases.json",
    "data/batches/batch_001.json": DATA / "batches" / "batch_001.json",
    "data/batches/batch_002.json": DATA / "batches" / "batch_002.json",
    "data/batches/batch_003.json": DATA / "batches" / "batch_003.json",
}

errors: list[str] = []


def error(path: str, message: str) -> None:
    errors.append(f"{path}: {message}")


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        error(str(path.relative_to(ROOT)), f"cannot load JSON ({exc})")
        return None


def is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def is_number(value: Any) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool))


def nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def check_keys(value: Any, required: set[str], path: str, exact: bool = True) -> bool:
    if not isinstance(value, dict):
        error(path, "must be an object")
        return False
    missing = required - value.keys()
    extra = value.keys() - required if exact else set()
    if missing:
        error(path, f"missing fields: {', '.join(sorted(missing))}")
    if extra:
        error(path, f"unexpected fields: {', '.join(sorted(extra))}")
    return not missing


def parse_timestamp(value: Any, path: str) -> datetime | None:
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})", value
    ):
        error(path, "must be an RFC3339-ish timestamp with an explicit timezone")
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        error(path, "is not a valid datetime")
        return None
    if parsed.utcoffset() is None:
        error(path, "must be timezone-aware")
        return None
    return parsed


def valid_date(value: Any, path: str) -> bool:
    if value is None:
        return True
    if not isinstance(value, str):
        error(path, "must be an ISO date or null")
        return False
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        error(path, "must be a valid ISO date")
        return False


def validate_email(item: Any, path: str) -> datetime | None:
    if not check_keys(item, EMAIL_FIELDS, path):
        return None
    for field in ("email_id", "thread_id", "from_name", "from_email", "to", "subject", "body"):
        if not nonempty_string(item.get(field)):
            error(f"{path}.{field}", "must be a non-empty string")
    if isinstance(item.get("from_email"), str) and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", item["from_email"]):
        error(f"{path}.from_email", "must be an email address")
    if isinstance(item.get("to"), str) and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", item["to"]):
        error(f"{path}.to", "must be an email address")
    index = item.get("message_index")
    if not is_int(index) or index < 0:
        error(f"{path}.message_index", "must be a non-negative integer")
    for field in ("cc", "attachments"):
        values = item.get(field)
        if not isinstance(values, list) or any(not nonempty_string(value) for value in values):
            error(f"{path}.{field}", "must be an array of non-empty strings")
    if type(item.get("is_reply")) is not bool:
        error(f"{path}.is_reply", "must be a boolean")
    elif is_int(index) and item["is_reply"] != (index > 0):
        error(f"{path}.is_reply", "must be true exactly when message_index is greater than zero")
    return parse_timestamp(item.get("received_at"), f"{path}.received_at")


def validate_task(task: Any, path: str, include_key: bool = False) -> bool:
    fields = TASK_FIELDS | ({"task_key"} if include_key else set())
    if not check_keys(task, fields, path):
        return False
    for field in ("source_email_id", "thread_id", "title", "description", "assignee_id", "category", "priority"):
        if not nonempty_string(task.get(field)):
            error(f"{path}.{field}", "must be a non-empty string")
    if include_key and not nonempty_string(task.get("task_key")):
        error(f"{path}.task_key", "must be a non-empty string")
    assignee = task.get("assignee_id")
    category = task.get("category")
    if assignee not in ASSIGNEE_CATEGORY:
        error(f"{path}.assignee_id", f"must be one of {sorted(ASSIGNEE_CATEGORY)}")
    elif category != ASSIGNEE_CATEGORY[assignee]:
        error(f"{path}.category", "does not match assignee_id")
    if category not in CATEGORIES:
        error(f"{path}.category", f"must be one of {sorted(CATEGORIES)}")
    if task.get("priority") not in PRIORITIES:
        error(f"{path}.priority", f"must be one of {sorted(PRIORITIES)}")
    valid_date(task.get("due_date"), f"{path}.due_date")
    deal = task.get("deal_value_inr")
    if deal is not None and (not is_int(deal) or deal < 0):
        error(f"{path}.deal_value_inr", "must be a non-negative integer or null")
    company = task.get("company_name")
    if company is not None and not nonempty_string(company):
        error(f"{path}.company_name", "must be a non-empty string or null")
    confidence = task.get("confidence")
    if not is_number(confidence) or not 0 <= confidence <= 1:
        error(f"{path}.confidence", "must be a number from 0 to 1")
    return True


def validate_decision(item: Any, path: str) -> None:
    if not isinstance(item, dict):
        error(path, "must be an object")
        return
    operation = item.get("operation")
    expected_fields = DECISION_FIELDS | ({"metadata_patch"} if operation == "update" else set())
    if not check_keys(item, expected_fields, path):
        return
    for field in ("email_id", "thread_id", "rationale"):
        if not nonempty_string(item.get(field)):
            error(f"{path}.{field}", "must be a non-empty string")
    if not is_int(item.get("message_index")) or item["message_index"] < 0:
        error(f"{path}.message_index", "must be a non-negative integer")
    if operation not in OPERATIONS:
        error(f"{path}.operation", f"must be one of {sorted(OPERATIONS)}")
    evidence = item.get("evidence")
    if not isinstance(evidence, list) or not evidence or any(not nonempty_string(value) for value in evidence):
        error(f"{path}.evidence", "must be a non-empty array of non-empty strings")
    confidence_range = item.get("confidence_range")
    if (not isinstance(confidence_range, list) or len(confidence_range) != 2
            or any(not is_number(value) for value in confidence_range)):
        error(f"{path}.confidence_range", "must be a two-number array")
    elif not 0 <= confidence_range[0] <= confidence_range[1] <= 1:
        error(f"{path}.confidence_range", "must be ordered within 0..1")
    if not isinstance(item.get("facets"), dict):
        error(f"{path}.facets", "must be an object")

    task, patch, reason, task_key = (item.get(key) for key in (
        "expected_task", "expected_patch", "skip_reason", "task_key"
    ))
    if operation == "create":
        validate_task(task, f"{path}.expected_task")
        if patch is not None or reason is not None or not nonempty_string(task_key):
            error(path, "create requires a task/task_key and null patch/skip_reason")
        if isinstance(task, dict) and task.get("source_email_id") != item.get("email_id"):
            error(f"{path}.expected_task.source_email_id", "must equal the creating email_id")
        if isinstance(task, dict) and task.get("thread_id") != item.get("thread_id"):
            error(f"{path}.expected_task.thread_id", "must equal the decision thread_id")
    elif operation == "update":
        if task is not None or reason is not None or not nonempty_string(task_key):
            error(path, "update requires a patch/task_key and null task/skip_reason")
        if not isinstance(patch, dict) or not patch:
            error(f"{path}.expected_patch", "must be a non-empty object")
        else:
            unknown = patch.keys() - MUTABLE_TASK_FIELDS
            if unknown:
                error(f"{path}.expected_patch", f"unknown or immutable task fields: {', '.join(sorted(unknown))}")
        if not isinstance(item.get("metadata_patch"), dict):
            error(f"{path}.metadata_patch", "must be an object")
    elif operation == "skip":
        if task is not None or patch is not None or reason not in SKIP_REASONS:
            error(path, "skip requires an enum skip_reason and null task/patch")
        if item.get("message_index") == 0 and task_key is not None:
            error(f"{path}.task_key", "initial skip must not reference a task")
        if item.get("message_index", 0) > 0 and not nonempty_string(task_key):
            error(f"{path}.task_key", "reply skip must reference its existing task")
    elif operation == "noop":
        if any(value is not None for value in (task, patch, reason)) or not nonempty_string(task_key):
            error(path, "noop requires a task_key and null task/patch/skip_reason")


def duplicates(values: list[Any]) -> list[Any]:
    counts = Counter(values)
    return sorted((value for value, count in counts.items() if count > 1), key=repr)


def validate_threads(emails: list[dict[str, Any]], timestamps: dict[str, datetime]) -> None:
    threads: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in emails:
        if isinstance(item, dict) and isinstance(item.get("thread_id"), str):
            threads[item["thread_id"]].append(item)
    for thread_id, messages in threads.items():
        if not all(is_int(item.get("message_index")) for item in messages):
            continue
        ordered = sorted(messages, key=lambda item: item["message_index"])
        indexes = [item["message_index"] for item in ordered]
        if indexes != list(range(len(ordered))):
            error(f"inbox.thread[{thread_id}]", f"message indexes are not contiguous from zero: {indexes}")
        times = [timestamps.get(item.get("email_id")) for item in ordered]
        if all(value is not None for value in times) and any(a >= b for a, b in zip(times, times[1:])):
            error(f"inbox.thread[{thread_id}]", "timestamps are not strictly chronological")


def fixture_is_invalid(case_id: str, emails: Any) -> bool:
    if not isinstance(emails, list):
        return False
    first = emails[0] if emails and isinstance(emails[0], dict) else {}
    tests: dict[str, Callable[[], bool]] = {
        "missing_email_id": lambda: "email_id" not in first,
        "empty_thread_id": lambda: isinstance(first.get("thread_id"), str) and not first["thread_id"].strip(),
        "invalid_timestamp": lambda: not isinstance(first.get("received_at"), str) or re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})", first["received_at"]
        ) is None,
        "cc_not_array": lambda: not isinstance(first.get("cc"), list),
        "attachments_not_array": lambda: not isinstance(first.get("attachments"), list),
        "is_reply_not_boolean": lambda: type(first.get("is_reply")) is not bool,
        "negative_message_index": lambda: not is_int(first.get("message_index")) or first["message_index"] < 0,
        "invalid_sender_email": lambda: not isinstance(first.get("from_email"), str) or re.fullmatch(
            r"[^\s@]+@[^\s@]+\.[^\s@]+", first["from_email"]
        ) is None,
        "duplicate_email_id_in_request": lambda: len(emails) >= 2 and len({item.get("email_id") for item in emails if isinstance(item, dict)}) < len(emails),
        "orphan_reply_index": lambda: bool(first.get("is_reply")) and first.get("message_index") != 0,
        "batch_over_limit": lambda: len(emails) > 100,
    }
    try:
        return tests[case_id]()
    except (KeyError, TypeError, ValueError):
        return False


def validate_fixtures(document: Any, production_ids: set[str]) -> int:
    if not check_keys(document, {"schema_version", "description", "cases"}, "invalid_fixtures"):
        return 0
    if document.get("schema_version") != SCHEMA_VERSION:
        error("invalid_fixtures.schema_version", f"must equal {SCHEMA_VERSION}")
    if not nonempty_string(document.get("description")) or "never ingest" not in document["description"].lower():
        error("invalid_fixtures.description", "must explicitly isolate fixtures from production ingestion")
    cases = document.get("cases")
    if not isinstance(cases, list):
        error("invalid_fixtures.cases", "must be an array")
        return 0
    ids = [case.get("case_id") for case in cases if isinstance(case, dict)]
    if set(ids) != set(EXPECTED_FIXTURES) or len(ids) != len(EXPECTED_FIXTURES):
        error("invalid_fixtures.cases", "must contain each expected case exactly once")
    for index, case in enumerate(cases):
        path = f"invalid_fixtures.cases[{index}]"
        if not check_keys(case, {"case_id", "expected_error", "expected_path", "payload"}, path):
            continue
        case_id = case.get("case_id")
        if case_id not in EXPECTED_FIXTURES:
            error(f"{path}.case_id", "is not an expected fixture")
            continue
        if (case.get("expected_error"), case.get("expected_path")) != EXPECTED_FIXTURES[case_id]:
            error(path, "expected_error/expected_path metadata does not match the fixture contract")
        payload = case.get("payload")
        if not check_keys(payload, {"candidate_id", "emails"}, f"{path}.payload"):
            continue
        if not nonempty_string(payload.get("candidate_id")):
            error(f"{path}.payload.candidate_id", "must be a non-empty string")
        fixture_emails = payload.get("emails")
        if not fixture_is_invalid(case_id, fixture_emails):
            error(f"{path}.payload", "does not exhibit its declared invalid condition")
        if isinstance(fixture_emails, list):
            special_ids = {
                item.get("email_id") for item in fixture_emails if isinstance(item, dict)
                and isinstance(item.get("email_id"), str) and item["email_id"].startswith("em_invalid_")
            }
            if special_ids & production_ids:
                error(f"{path}.payload.emails", "fixture-only IDs leaked into production")
    return len(cases)


def validate_edges(emails: list[dict[str, Any]], decisions: list[dict[str, Any]], tasks: list[dict[str, Any]]) -> list[str]:
    emails = [item for item in emails if isinstance(item, dict)]
    decisions = [item for item in decisions if isinstance(item, dict)]
    tasks = [item for item in tasks if isinstance(item, dict)]
    creates = [item for item in decisions if item.get("operation") == "create" and isinstance(item.get("expected_task"), dict)]
    updates = [item for item in decisions if item.get("operation") == "update" and isinstance(item.get("expected_patch"), dict)]
    email_text = "\n".join(f"{item.get('subject', '')}\n{item.get('body', '')}" for item in emails)
    initial_by_key = {item.get("task_key"): item["expected_task"] for item in creates}
    final_by_key = {item.get("task_key"): item for item in tasks}
    transitions = {
        (initial.get("category"), final_by_key[key].get("category"))
        for key, initial in initial_by_key.items() if key in final_by_key
    }
    checks = {
        "all operations": {item.get("operation") for item in decisions} == OPERATIONS,
        "all task categories": {item.get("category") for item in tasks} == CATEGORIES,
        "all skip reasons": {item.get("skip_reason") for item in decisions if item.get("operation") == "skip"} == SKIP_REASONS,
        "INR threshold boundaries": all(any(task.get("deal_value_inr") == value and task.get("category") == category for task in (item["expected_task"] for item in creates)) for value, category in ((999999, "smb_enquiry"), (1000000, "smb_enquiry"), (1000001, "enterprise_rfp"))),
        "PSU below-threshold override": any(item.get("facets", {}).get("organization_type") == "psu" and item["expected_task"].get("deal_value_inr", 1000001) <= 1000000 and item["expected_task"].get("category") == "enterprise_rfp" for item in creates),
        "route-changing replies": {("smb_enquiry", "enterprise_rfp"), ("triage", "marketing"), ("triage", "enterprise_rfp"), ("alliances", "smb_enquiry")} <= transitions,
        "multi-update threads": any(sum(1 for item in updates if item.get("thread_id") == thread) >= 2 for thread in {item.get("thread_id") for item in updates}),
        "no-effect replies": any(item.get("operation") == "noop" for item in decisions) and any(item.get("operation") == "skip" and item.get("message_index", 0) > 0 for item in decisions),
        "prompt-injection resistance": any(item.get("facets", {}).get("topics") == ["prompt_injection"] for item in decisions) and "Ignore previous instructions" in email_text,
        "marketing lookalike spam": any(item.get("operation") == "skip" and item.get("facets", {}).get("marketing_lookalike") is True for item in decisions),
        "format and language variation": "<p>" in email_text and "Koi demo slot" in email_text,
        "attachments": any(item.get("attachments") for item in emails),
        "priority coverage": {item.get("priority") for item in tasks} == PRIORITIES,
        "finance amounts excluded": all(item["expected_task"].get("deal_value_inr") is None for item in creates if item["expected_task"].get("category") == "finance"),
    }
    missing = [name for name, present in checks.items() if not present]
    for name in missing:
        error("edge_coverage", f"missing {name}")
    return list(checks)


def main() -> int:
    documents = {name: load_json(path) for name, path in TRACKED_FILES.items()}
    manifest = load_json(DATA / "manifest.json")

    inbox = documents["data/inbox.json"]
    emails: list[dict[str, Any]] = inbox if isinstance(inbox, list) else []
    if not isinstance(inbox, list):
        error("inbox", "must be an array")
    if len(emails) != 250:
        error("inbox", f"must contain exactly 250 messages, found {len(emails)}")
    timestamps: dict[str, datetime] = {}
    for index, item in enumerate(emails):
        parsed = validate_email(item, f"inbox[{index}]")
        if parsed is not None and isinstance(item, dict) and isinstance(item.get("email_id"), str):
            timestamps[item["email_id"]] = parsed
    email_ids = [item.get("email_id") for item in emails if isinstance(item, dict)]
    duplicate_email_ids = duplicates(email_ids)
    if duplicate_email_ids:
        error("inbox.email_id", f"duplicate IDs: {duplicate_email_ids}")
    thread_ids = {item.get("thread_id") for item in emails if isinstance(item, dict)}
    if len(thread_ids) != 200:
        error("inbox.thread_id", f"must contain exactly 200 unique threads, found {len(thread_ids)}")
    validate_threads(emails, timestamps)

    decision_doc = documents["data/ground_truth/expected_decisions.json"]
    if check_keys(decision_doc, {"schema_version", "decisions"}, "expected_decisions"):
        if decision_doc.get("schema_version") != SCHEMA_VERSION:
            error("expected_decisions.schema_version", f"must equal {SCHEMA_VERSION}")
        raw_decisions = decision_doc.get("decisions")
    else:
        raw_decisions = None
    decisions: list[dict[str, Any]] = raw_decisions if isinstance(raw_decisions, list) else []
    if not isinstance(raw_decisions, list):
        error("expected_decisions.decisions", "must be an array")
    if len(decisions) != 250:
        error("expected_decisions.decisions", f"must contain exactly 250 decisions, found {len(decisions)}")
    for index, item in enumerate(decisions):
        validate_decision(item, f"expected_decisions.decisions[{index}]")
    decision_ids = [item.get("email_id") for item in decisions if isinstance(item, dict)]
    if duplicates(decision_ids):
        error("expected_decisions.email_id", f"duplicate IDs: {duplicates(decision_ids)}")
    if Counter(decision_ids) != Counter(email_ids):
        error("expected_decisions", "must map one-to-one to inbox email IDs")
    email_by_id = {item.get("email_id"): item for item in emails if isinstance(item, dict)}
    decision_by_id = {item.get("email_id"): item for item in decisions if isinstance(item, dict)}
    for email_id in set(email_by_id) & set(decision_by_id):
        email_item, decision = email_by_id[email_id], decision_by_id[email_id]
        for field in ("thread_id", "message_index"):
            if decision.get(field) != email_item.get(field):
                error(f"expected_decisions[{email_id}].{field}", "does not match source email")

    task_doc = documents["data/ground_truth/expected_tasks.json"]
    if check_keys(task_doc, {"schema_version", "tasks"}, "expected_tasks"):
        if task_doc.get("schema_version") != SCHEMA_VERSION:
            error("expected_tasks.schema_version", f"must equal {SCHEMA_VERSION}")
        raw_tasks = task_doc.get("tasks")
    else:
        raw_tasks = None
    tasks: list[dict[str, Any]] = raw_tasks if isinstance(raw_tasks, list) else []
    if not isinstance(raw_tasks, list):
        error("expected_tasks.tasks", "must be an array")
    for index, task in enumerate(tasks):
        validate_task(task, f"expected_tasks.tasks[{index}]", include_key=True)
    task_keys = [task.get("task_key") for task in tasks if isinstance(task, dict)]
    if duplicates(task_keys):
        error("expected_tasks.task_key", f"duplicate keys: {duplicates(task_keys)}")

    state: dict[str, dict[str, Any]] = {}
    for index, decision in enumerate(decisions):
        if not isinstance(decision, dict):
            continue
        operation, key = decision.get("operation"), decision.get("task_key")
        if operation == "create" and isinstance(key, str) and isinstance(decision.get("expected_task"), dict):
            if key in state:
                error(f"replay[{index}]", f"duplicate create for {key}")
            else:
                state[key] = dict(decision["expected_task"])
        elif operation == "update" and isinstance(key, str) and isinstance(decision.get("expected_patch"), dict):
            if key not in state:
                error(f"replay[{index}]", f"update references missing task {key}")
            else:
                before = dict(state[key])
                source_id = state[key].get("source_email_id")
                state[key].update(decision["expected_patch"])
                if state[key].get("source_email_id") != source_id:
                    error(f"replay[{index}]", f"changed immutable source_email_id for {key}")
                if state[key].get("thread_id") != decision.get("thread_id"):
                    error(f"replay[{index}]", f"update thread does not match task {key}")
                if state[key] == before:
                    error(f"replay[{index}]", "update patch has no effect; use noop instead")
        elif operation in {"skip", "noop"} and isinstance(key, str) and decision.get("message_index", 0) > 0 and key not in state:
            error(f"replay[{index}]", f"{operation} references missing task {key}")
    replayed = [{"task_key": key, **task} for key, task in state.items()]
    replayed.sort(key=lambda item: item.get("thread_id", ""))
    expected_sorted = sorted(tasks, key=lambda item: item.get("thread_id", "") if isinstance(item, dict) else "")
    if replayed != expected_sorted:
        error("replay", "create/update replay does not exactly match expected_tasks")
    for task in tasks:
        if isinstance(task, dict) and task.get("source_email_id") not in email_by_id:
            error(f"expected_tasks[{task.get('task_key')}].source_email_id", "does not reference an inbox email")

    batch_names = ["batch_001.json", "batch_002.json", "batch_003.json"]
    batches = [documents[f"data/batches/{name}"] for name in batch_names]
    sizes = [len(batch) if isinstance(batch, list) else -1 for batch in batches]
    if sizes != [100, 100, 50]:
        error("batches", f"sizes must be [100, 100, 50], found {sizes}")
    if all(isinstance(batch, list) for batch in batches) and [item for batch in batches for item in batch] != emails:
        error("batches", "batch concatenation does not exactly equal inbox order and content")

    eval_doc = documents["data/eval/eval_60.json"]
    if check_keys(eval_doc, {"schema_version", "review_status", "warning", "items"}, "eval"):
        if eval_doc.get("schema_version") != SCHEMA_VERSION:
            error("eval.schema_version", f"must equal {SCHEMA_VERSION}")
        if eval_doc.get("review_status") != "draft_requires_manual_review":
            error("eval.review_status", "must remain draft_requires_manual_review")
        if not nonempty_string(eval_doc.get("warning")):
            error("eval.warning", "must be a non-empty string")
        raw_eval = eval_doc.get("items")
    else:
        raw_eval = None
    eval_items = raw_eval if isinstance(raw_eval, list) else []
    if len(eval_items) != 60:
        error("eval.items", f"must contain exactly 60 items, found {len(eval_items)}")
    eval_ids: list[Any] = []
    for index, item in enumerate(eval_items):
        path = f"eval.items[{index}]"
        if not check_keys(item, {"email", "label"}, path):
            continue
        email_id = item["email"].get("email_id") if isinstance(item.get("email"), dict) else None
        eval_ids.append(email_id)
        if email_by_id.get(email_id) != item.get("email"):
            error(f"{path}.email", "does not exactly match its inbox source")
        if decision_by_id.get(email_id) != item.get("label"):
            error(f"{path}.label", "does not exactly match its expected decision")
    if len(set(eval_ids)) != len(eval_ids):
        error("eval.items", "email IDs must be unique")

    roster = documents["data/team_roster.json"]
    if check_keys(roster, {"team"}, "team_roster"):
        team = roster.get("team")
        if not isinstance(team, list) or len(team) != len(ASSIGNEE_CATEGORY):
            error("team_roster.team", "must contain exactly six members")
        elif {member.get("user_id") for member in team if isinstance(member, dict)} != set(ASSIGNEE_CATEGORY):
            error("team_roster.team", "user IDs do not match task assignee enum")

    fixture_count = validate_fixtures(
        documents["data/fixtures/invalid_ingest_cases.json"],
        {value for value in email_ids if isinstance(value, str)},
    )
    edge_names = validate_edges(emails, decisions, tasks)

    if check_keys(manifest, {
        "schema_version", "generator_seed", "message_count", "thread_count",
        "initial_message_count", "reply_count", "operation_counts",
        "initial_scenario_counts", "final_task_count", "final_category_counts",
        "batch_files", "batch_sizes", "eval_count", "files",
    }, "manifest"):
        expected_counts = {
            "schema_version": SCHEMA_VERSION,
            "generator_seed": 20260808,
            "message_count": len(emails),
            "thread_count": len(thread_ids),
            "initial_message_count": sum(item.get("message_index") == 0 for item in emails if isinstance(item, dict)),
            "reply_count": sum(is_int(item.get("message_index")) and item["message_index"] > 0 for item in emails if isinstance(item, dict)),
            "operation_counts": dict(sorted(Counter(item.get("operation") for item in decisions if isinstance(item, dict)).items())),
            "initial_scenario_counts": EXPECTED_INITIAL_SCENARIOS,
            "final_task_count": len(tasks),
            "final_category_counts": dict(sorted(Counter(item.get("category") for item in tasks if isinstance(item, dict)).items())),
            "batch_files": batch_names,
            "batch_sizes": [100, 100, 50],
            "eval_count": len(eval_items),
        }
        for field, expected in expected_counts.items():
            if manifest.get(field) != expected:
                error(f"manifest.{field}", f"does not match computed/expected value {expected!r}")
        if manifest.get("operation_counts") != EXPECTED_OPERATION_COUNTS:
            error("manifest.operation_counts", f"must equal pinned coverage {EXPECTED_OPERATION_COUNTS!r}")
        if manifest.get("final_category_counts") != EXPECTED_FINAL_CATEGORIES:
            error("manifest.final_category_counts", f"must equal pinned coverage {EXPECTED_FINAL_CATEGORIES!r}")
        hashes = manifest.get("files")
        if not isinstance(hashes, dict) or set(hashes) != set(TRACKED_FILES):
            error("manifest.files", "must list exactly the nine tracked generated artifacts")
        else:
            for name, path in TRACKED_FILES.items():
                try:
                    actual = hashlib.sha256(path.read_bytes()).hexdigest()
                except OSError as exc:
                    error(f"manifest.files.{name}", f"cannot hash file ({exc})")
                    continue
                if hashes.get(name) != actual:
                    error(f"manifest.files.{name}", f"SHA256 mismatch (actual {actual})")

    if errors:
        print(f"Dataset validation failed with {len(errors)} error(s):", file=sys.stderr)
        for item in errors:
            print(f"- {item}", file=sys.stderr)
        return 1

    operations = Counter(item["operation"] for item in decisions)
    categories = Counter(item["category"] for item in tasks)
    print(
        "Dataset valid: "
        f"{len(emails)} messages / {len(thread_ids)} threads / {len(tasks)} tasks; "
        f"operations {dict(sorted(operations.items()))}; "
        f"categories {dict(sorted(categories.items()))}; "
        f"{len(edge_names)} edge checks, {fixture_count} invalid fixtures, {len(eval_items)} draft eval items."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
