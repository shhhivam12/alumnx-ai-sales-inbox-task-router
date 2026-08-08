from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from backend.app.config import LOCKED_CANDIDATE_ID


ChatIntent = Literal[
    "count_category", "compare_categories", "compare_category_and_skip_reason",
    "list_triage", "spurious_rate", "list_priority_confidence", "count_subtypes",
    "count_topic", "sum_deal_value", "threads_with_updates", "out_of_scope", "unsupported",
]


class ChatScope(BaseModel):
    type: Literal["run", "batch", "all"] = "all"
    id: str | None = None

    @model_validator(mode="after")
    def scope_id_required(self) -> "ChatScope":
        if self.type != "all" and not self.id:
            raise ValueError("scope id required for run or batch")
        return self


class ChatRequest(BaseModel):
    candidate_id: str
    query: str = Field(min_length=1, max_length=2000)
    scope: ChatScope = Field(default_factory=ChatScope)

    @model_validator(mode="after")
    def candidate_matches(self) -> "ChatRequest":
        self.candidate_id = self.candidate_id.strip().lower()
        if self.candidate_id != LOCKED_CANDIDATE_ID:
            raise ValueError("candidate_id mismatch")
        return self


class ChatPlan(BaseModel):
    intent: ChatIntent
    categories: list[str] = Field(default_factory=list)
    skip_reasons: list[str] = Field(default_factory=list)
    priority: str | None = None
    max_confidence: float | None = Field(default=None, ge=0, le=1)
    topic: str | None = None
    subtype: str | None = None


class ChatResponse(BaseModel):
    answer: str
    supporting_data: dict[str, Any]
    scope: ChatScope
