from __future__ import annotations

from collections import Counter
from datetime import datetime
import json
import logging
import re
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from backend.app.config import Settings
from backend.app.domain.chat_models import ANALYTICS_FIELDS, ChatPlan


logger = logging.getLogger(__name__)


class PhrasedAnswer(BaseModel):
    answer: str = Field(min_length=1, max_length=4000)


def _number_tokens(value: str) -> Counter[str]:
    return Counter(re.findall(r"-?\d+(?:\.\d+)?%?", value.replace(",", "")))


def _preserves_subject(plan: ChatPlan, value: str) -> bool:
    text = value.lower()
    required_groups = {
        "count_category": (("rfp", "proposal", "tender"),),
        "compare_categories": (("rfp", "proposal", "tender"), ("marketing", "sponsorship", "webinar")),
        "compare_category_and_skip_reason": (("marketing", "sponsorship", "webinar"), ("spam", "vendor")),
        "list_triage": (("triage", "manual review"),),
        "spurious_rate": (("spurious", "false positive"),),
        "list_priority_confidence": (("high-priority", "high priority", "urgent"), ("confidence", "certainty")),
        "count_subtypes": (("alliance", "partnership"),),
        "count_topic": (("gst",),),
        "sum_deal_value": (("value", "inr"), ("rfp", "proposal", "tender")),
        "threads_with_updates": (("thread", "conversation"), ("update", "changed")),
    }
    return all(any(term in text for term in group) for group in required_groups.get(plan.intent, ()))


class ChatAnswerService:
    """Optionally lets Gemini improve wording without letting it compute facts.

    The model never sees the user's raw prompt. It receives only an allowlisted
    plan, backend-computed supporting data, and an already-grounded draft. Any
    response that adds, removes, or changes a number is rejected.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: Any | None = None
        if settings.gemini_api_key:
            try:
                from google import genai

                self._client = genai.Client(api_key=settings.gemini_api_key)
            except ImportError:
                logger.warning("Gemini SDK unavailable; using grounded chat templates")

    def plan(self, question: str, fallback: ChatPlan) -> ChatPlan:
        """Let Gemini select a validated read-only plan, never SQL or facts."""
        if not self._client or fallback.intent != "unsupported":
            return fallback
        schema_summary = {dataset: sorted(fields) for dataset, fields in ANALYTICS_FIELDS.items()}
        prompt = (
            "Translate the user's analytics question into one read-only structured plan. "
            "Return intent=analytics with an analytics object, or intent=unsupported when the requested fact is not in the schema. "
            "Never invent a field, value, fact, count, SQL fragment, or write action. Choose current_tasks for the current task state; "
            "choose decisions for one row per processed email and skipped-email facts; choose threads for message/update history; "
            "choose events for task event history; choose feedback for human labels; choose runs for ingestion counters. "
            "Use assignee IDs u_aarti, u_rohit, u_meera, u_karan, u_divya, or u_triage when names are mentioned. "
            "Valid categories are enterprise_rfp, smb_enquiry, marketing, alliances, finance, and triage. "
            "Valid priorities are high, medium, and low. Low confidence means confidence <= 0.54. "
            "For list queries select only relevant fields and use a maximum limit of 20. "
            f"Today's date in Asia/Kolkata is {datetime.now(ZoneInfo('Asia/Kolkata')).date().isoformat()}.\n"
            f"ALLOWLISTED_SCHEMA: {json.dumps(schema_summary, sort_keys=True)}\n"
            f"USER_QUESTION: {question}"
        )
        try:
            response = self._client.models.generate_content(
                model=self.settings.gemini_model,
                contents=prompt,
                config={
                    "temperature": 0,
                    "max_output_tokens": min(2048, self.settings.gemini_max_output_tokens),
                    "response_mime_type": "application/json",
                    "response_json_schema": ChatPlan.model_json_schema(),
                },
            )
            parsed = getattr(response, "parsed", None)
            result = ChatPlan.model_validate(parsed) if parsed is not None else ChatPlan.model_validate_json(response.text)
            if result.intent not in {"analytics", "unsupported", "out_of_scope"}:
                logger.warning("Gemini chat planner emitted a non-analytics intent; using safe fallback")
                return fallback
            return result
        except Exception:
            logger.warning("Gemini chat planning failed validation; using safe fallback", exc_info=True)
            return fallback

    def phrase(self, plan: ChatPlan, supporting_data: dict[str, Any], grounded_answer: str) -> str:
        if not self._client or plan.intent in {"out_of_scope", "unsupported"}:
            return grounded_answer

        prompt = (
            "Rewrite the grounded answer for a sales operations user. Be concise and plain. "
            "Do not add, remove, reformat, calculate, or change any number. Do not claim any action. "
            "The supporting data is authoritative. Return JSON only.\n\n"
            f"INTENT: {plan.intent}\n"
            f"SUPPORTING_DATA: {json.dumps(supporting_data, ensure_ascii=False, default=str)}\n"
            f"GROUNDED_ANSWER: {grounded_answer}"
        )
        try:
            response = self._client.models.generate_content(
                model=self.settings.gemini_model,
                contents=prompt,
                config={
                    "temperature": self.settings.gemini_temperature,
                    "max_output_tokens": min(1024, self.settings.gemini_max_output_tokens),
                    "response_mime_type": "application/json",
                    "response_json_schema": PhrasedAnswer.model_json_schema(),
                },
            )
            parsed = getattr(response, "parsed", None)
            result = PhrasedAnswer.model_validate(parsed) if parsed is not None else PhrasedAnswer.model_validate_json(response.text)
            candidate = result.answer.strip()
            if _number_tokens(candidate) != _number_tokens(grounded_answer) or not _preserves_subject(plan, candidate):
                logger.warning("Gemini chat phrasing changed grounded evidence; using grounded template")
                return grounded_answer
            return candidate
        except Exception:
            logger.warning("Gemini chat phrasing failed; using grounded template", exc_info=True)
            return grounded_answer
