from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.config import LOCKED_CANDIDATE_ID
from backend.app.domain.enums import Actionability, AssigneeId, Category, Operation, Priority, SkipReason


class TaskPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    source_email_id: str = Field(min_length=1, max_length=128)
    thread_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    assignee_id: AssigneeId
    category: Category
    priority: Priority
    due_date: date | None
    deal_value_inr: int | None = Field(strict=True, ge=0)
    company_name: str | None = Field(max_length=256)
    confidence: float = Field(ge=0, le=1)

    @field_validator("candidate_id")
    @classmethod
    def candidate_matches(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized != LOCKED_CANDIDATE_ID:
            raise ValueError("candidate_id does not match the configured submission identity")
        return normalized

    @field_validator("source_email_id", "thread_id", "title")
    @classmethod
    def identifiers_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value.strip()


class TaskPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    assignee_id: AssigneeId | None = None
    category: Category | None = None
    priority: Priority | None = None
    due_date: date | None = None
    deal_value_inr: int | None = Field(default=None, strict=True, ge=0)
    company_name: str | None = Field(default=None, max_length=256)
    confidence: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def required_task_fields_cannot_be_cleared(self) -> "TaskPatch":
        required = {"title", "assignee_id", "category", "priority", "confidence"}
        for field in required & self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        if not self.model_fields_set:
            raise ValueError("patch must contain at least one mutable field")
        return self


class TaskRecord(TaskPayload):
    model_config = ConfigDict(extra="ignore")

    task_id: str
    created_at: datetime


class TaskCreatedResponse(BaseModel):
    task_id: str
    candidate_id: str
    source_email_id: str
    created_at: datetime


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
