from __future__ import annotations

from backend.app.domain.chat_models import ChatPlan


ASSIGNEE_LABELS = {
    "u_aarti": "Aarti", "u_rohit": "Rohit", "u_meera": "Meera",
    "u_karan": "Karan", "u_divya": "Divya", "u_triage": "Triage Queue",
}
DATASET_LABELS = {
    "current_tasks": "current tasks", "decisions": "email decisions", "threads": "threads",
    "events": "task events", "feedback": "feedback records", "runs": "ingestion runs",
}
SINGULAR_DATASET_LABELS = {
    "current_tasks": "current task", "decisions": "email decision", "threads": "thread",
    "events": "task event", "feedback": "feedback record", "runs": "ingestion run",
}


def _dataset_label(dataset: str, count: int) -> str:
    return SINGULAR_DATASET_LABELS[dataset] if count == 1 else DATASET_LABELS[dataset]


def _display_value(field: str, value: object) -> str:
    if field == "assignee_id":
        return ASSIGNEE_LABELS.get(str(value), str(value))
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value).replace("_", " ")


def _filter_summary(filters: list[dict]) -> str:
    parts = []
    for item in filters:
        field, operator, value = item["field"], item["operator"], item.get("value")
        label = field.replace("_", " ")
        if field == "assignee_id" and operator == "eq":
            parts.append(f"assigned to {_display_value(field, value)}")
        elif operator == "eq":
            parts.append(f"with {label} {_display_value(field, value)}")
        elif operator == "is_null":
            parts.append(f"with no {label}")
        elif operator == "not_null":
            parts.append(f"with a {label}")
        elif operator == "contains":
            parts.append(f"whose {label} contains {_display_value(field, value)}")
        elif operator == "in":
            values = ", ".join(_display_value(field, entry) for entry in (value or []))
            parts.append(f"with {label} in {values}")
        else:
            words = {"gte": "at or above", "lte": "at or below", "gt": "above", "lt": "below", "neq": "not"}
            parts.append(f"with {label} {words.get(operator, operator)} {_display_value(field, value)}")
    return " " + " and ".join(parts) if parts else ""


def _render_analytics(plan: ChatPlan, data: dict) -> tuple[str, str]:
    query = plan.analytics
    dataset = DATASET_LABELS[query.dataset]
    filters = _filter_summary(data.get("filters", []))
    if query.operation == "count":
        noun = _dataset_label(query.dataset, data["count"])
        verb = "is" if data["count"] == 1 else "are"
        return f"There {verb} {data['count']} {noun}{filters} in this scope.", "answered"
    if query.operation == "group_count":
        groups = data.get("groups", {})
        details = ", ".join(
            f"{_display_value(str(query.group_by), name)}: {count}" for name, count in groups.items()
        )
        return f"The {data['total_matches']} matching {dataset} group as follows: {details or 'no groups'}.", "answered"
    if query.operation == "list":
        details = "; ".join(
            ", ".join(f"{field.replace('_', ' ')}={_display_value(field, value)}" for field, value in item.items())
            for item in data.get("items", [])
        )
        if not details:
            return f"There are no {dataset}{filters} in this scope.", "answered"
        suffix = f" Showing {data['shown']} of {data['count']}: {details}."
        noun = _dataset_label(query.dataset, data["count"])
        return f"I found {data['count']} {noun}{filters}.{suffix}", "answered"

    metric = str(data.get("metric", "value")).replace("_", " ")
    value = data.get("value")
    if value is None:
        return f"The matching {dataset} have no stored numeric values for {metric}.", "answered"
    if query.metric == "deal_value_inr":
        rendered_value = f"INR {format_inr(int(value))}"
    elif query.metric == "confidence":
        rendered_value = f"{float(value):.3f}"
    else:
        rendered_value = str(value)
    operation = {"sum": "total", "average": "average", "minimum": "minimum", "maximum": "maximum"}[query.operation]
    return (
        f"The {operation} {metric} is {rendered_value}, using {data['values_used']} matching records; "
        f"{data['missing_values']} records had no numeric value.",
        "answered",
    )


def format_inr(value: int) -> str:
    digits = str(abs(value))
    if len(digits) <= 3:
        grouped = digits
    else:
        head, tail = digits[:-3], digits[-3:]
        parts = []
        while head:
            parts.append(head[-2:])
            head = head[:-2]
        grouped = ",".join(reversed(parts)) + "," + tail
    return ("-" if value < 0 else "") + grouped


def render_answer(plan: ChatPlan, data: dict) -> tuple[str, str]:
    if plan.intent == "analytics":
        return _render_analytics(plan, data)
    if plan.intent == "out_of_scope":
        return "I can analyze stored routing data, but this read-only product cannot send email or perform actions.", "refused"
    if plan.intent == "unsupported":
        return "That question cannot be answered from the stored, allowlisted analytics fields.", "unsupported"
    if plan.intent == "count_category": return f"There are {data['count']} {data['category']} email decisions in this scope.", "answered"
    if plan.intent == "compare_categories": return f"This scope contains {data.get('enterprise_rfp', 0)} enterprise RFP/proposal decisions and {data.get('marketing', 0)} marketing decisions.", "answered"
    if plan.intent == "compare_category_and_skip_reason": return f"There are {data['routed_count']} routed marketing decisions and {data['skipped_count']} skipped vendor-spam decisions; these are intentionally separate.", "answered"
    if plan.intent == "list_triage":
        details = "; ".join(
            f"{item.get('task_id') or item['thread_id']}: {str(item.get('reason') or 'reason unavailable')[:160]}"
            for item in data["items"]
        )
        suffix = f" {details}" if details else ""
        return f"There are {data['count']} current triage decisions.{suffix}", "answered"
    if plan.intent == "spurious_rate": return f"{data['confirmed_spurious']} confirmed spurious flags out of {data['unique_processed']} unique processed emails ({data['rate']:.2%}). Zero flags means none have been confirmed, not perfect accuracy.", "answered"
    if plan.intent == "list_priority_confidence":
        matches = ", ".join(
            f"{item.get('task_id') or item['thread_id']} ({item['confidence']})"
            for item in data["items"]
        )
        suffix = f": {matches}." if matches else "."
        return f"There are {data['count']} high-priority decisions at or below confidence {data['confidence_lte']}{suffix}", "answered"
    if plan.intent == "count_subtypes":
        subtypes = data.get("by_subtype", {})
        known = [(name.replace("_", " "), count) for name, count in subtypes.items() if name != "unavailable"]
        unavailable = subtypes.get("unavailable", 0)
        if not known:
            return f"There are {data['count']} alliance decisions, but the stored data does not contain a reliable reseller-versus-integration breakdown.", "answered"
        breakdown = ", ".join(f"{name}: {count}" for name, count in known)
        caveat = f"; subtype unavailable for {unavailable}" if unavailable else ""
        return f"There are {data['count']} alliance decisions ({breakdown}{caveat}).", "answered"
    if plan.intent == "count_topic": return f"There are {data['count']} decisions with topic {data['topic']}.", "answered"
    if plan.intent == "sum_deal_value": return f"The supported deal-value total is INR {format_inr(data['total_deal_value_inr'])}; {data['tasks_without_value']} of {data['task_count']} tasks have no stated value. The required Task API has no open/closed status, so this uses current RFP tasks.", "answered"
    if plan.intent == "threads_with_updates":
        details = ", ".join(f"{item['thread_id']} ({item['update_count']} updates)" for item in data["items"])
        suffix = f": {details}." if details else "."
        return f"There are {data['count']} threads with more than one confirmed update{suffix}", "answered"
    return "No supported answer is available.", "unsupported"
