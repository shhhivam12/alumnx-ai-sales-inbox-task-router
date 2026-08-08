from __future__ import annotations

from backend.app.domain.chat_models import ChatPlan


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
    if plan.intent == "out_of_scope":
        return "I can analyze stored routing data, but this read-only product cannot send email or perform actions.", "refused"
    if plan.intent == "unsupported":
        return "That question cannot be answered from the stored, allowlisted analytics fields.", "unsupported"
    if plan.intent == "count_category": return f"There are {data['count']} {data['category']} email decisions in this scope.", "answered"
    if plan.intent == "compare_categories": return f"This scope contains {data.get('enterprise_rfp', 0)} enterprise RFP/proposal decisions and {data.get('marketing', 0)} marketing decisions.", "answered"
    if plan.intent == "compare_category_and_skip_reason": return f"There are {data['routed_count']} routed marketing decisions and {data['skipped_count']} skipped vendor-spam decisions; these are intentionally separate.", "answered"
    if plan.intent == "list_triage": return f"There are {data['count']} current triage decisions. The supporting data contains their IDs, confidence, and stored reasons.", "answered"
    if plan.intent == "spurious_rate": return f"{data['confirmed_spurious']} confirmed spurious flags out of {data['unique_processed']} unique processed emails ({data['rate']:.2%}). Zero flags means none have been confirmed, not perfect accuracy.", "answered"
    if plan.intent == "list_priority_confidence": return f"There are {data['count']} high-priority decisions at or below confidence {data['confidence_lte']}.", "answered"
    if plan.intent == "count_subtypes": return f"There are {data['count']} alliance decisions. Missing subtype labels are reported as unavailable.", "answered"
    if plan.intent == "count_topic": return f"There are {data['count']} decisions with topic {data['topic']}.", "answered"
    if plan.intent == "sum_deal_value": return f"The supported deal-value total is INR {format_inr(data['total_deal_value_inr'])}; {data['tasks_without_value']} of {data['task_count']} tasks have no stated value. The shared Task API has no open/closed status, so this uses current RFP tasks.", "answered"
    if plan.intent == "threads_with_updates": return f"There are {data['count']} threads with more than one confirmed update.", "answered"
    return "No supported answer is available.", "unsupported"
