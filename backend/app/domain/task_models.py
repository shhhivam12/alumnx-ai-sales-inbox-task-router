from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from backend.app.domain.enums import Actionability, AssigneeId, Category, Operation, Priority, SkipReason


class TaskPayload(BaseModel):
    candidate_id: str
    source_email_id: str
    thread_id: str
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    assignee_id: AssigneeId
    category: Category
    priority: Priority
    due_date: date | None
    deal_value_inr: int | None = Field(ge=0)
    company_name: str | None
    confidence: float = Field(ge=0, le=1)


class TaskPatch(BaseModel):
    title: str | None = None
    description: str | None = None
    assignee_id: AssigneeId | None = None
    category: Category | None = None
    priority: Priority | None = None
    due_date: date | None = None
    deal_value_inr: int | None = None
    company_name: str | None = None
    confidence: float | None = None


class RoutingDecision(BaseModel):
    email_id: str
    thread_id: str
    operation: Operation
    actionability: Actionability
    skip_reason: SkipReason | None = None
    task: TaskPayload | None = None
    priority: Priority | None = None
    deadline_at: datetime | None = None
    confidence: float
    reasoning: str
    evidence: list[str] = Field(default_factory=list)
    primary_intents: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    intent_direction: str = "unclear"
    organization_type: str = "unknown"
    alliance_subtype: str | None = None
    marketing_subtype: str | None = None
    amount_mentions: list[dict[str, Any]] = Field(default_factory=list)
    deadline_mentions: list[dict[str, Any]] = Field(default_factory=list)
    degraded_mode: bool = False
    model_name: str | None = None
    prompt_version: str
