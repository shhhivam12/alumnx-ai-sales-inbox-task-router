from __future__ import annotations

from collections import Counter
import json
import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from backend.app.config import Settings
from backend.app.domain.chat_models import ChatPlan


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
