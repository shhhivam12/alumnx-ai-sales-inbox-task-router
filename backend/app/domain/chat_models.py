from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.app.config import LOCKED_CANDIDATE_ID


ChatIntent = Literal[
    "count_category", "compare_categories", "compare_category_and_skip_reason",
    "list_triage", "spurious_rate", "list_priority_confidence", "count_subtypes",
    "count_topic", "sum_deal_value", "threads_with_updates", "analytics", "out_of_scope", "unsupported",
]

AnalyticsDataset = Literal["current_tasks", "decisions", "threads", "events", "feedback", "runs"]
AnalyticsOperation = Literal["count", "list", "group_count", "sum", "average", "minimum", "maximum"]
FilterOperator = Literal["eq", "neq", "in", "contains", "gte", "lte", "gt", "lt", "is_null", "not_null"]
AnalyticsField = Literal[
    "task_id", "email_id", "source_email_id", "thread_id", "assignee_id", "category", "priority",
    "title", "description", "due_date", "deadline_at", "deal_value_inr", "company_name", "confidence", "reasoning", "evidence",
    "operation", "original_operation", "delivery_outcome", "actionability", "skip_reason", "primary_intents",
    "topics", "intent_direction", "organization_type", "alliance_subtype", "marketing_subtype", "degraded_mode",
    "amount_mentions", "deadline_mentions", "model_name", "prompt_version", "run_id", "client_batch_id", "created_at", "updated_at", "message_count",
    "update_count", "last_message_index", "reconciliation_status", "event_type", "status", "attempt_count",
    "confirmed_at", "label", "note", "received_count", "processed", "tasks_created", "tasks_updated", "skipped",
    "unchanged", "completed_at", "started_at",
]


ANALYTICS_FIELDS: dict[str, set[str]] = {
    "current_tasks": {
        "task_id", "email_id", "source_email_id", "thread_id", "title", "description", "assignee_id", "category", "priority", "due_date",
        "deal_value_inr", "company_name", "confidence", "reasoning", "evidence", "run_id", "client_batch_id",
        "message_count", "update_count", "last_message_index", "updated_at",
    },
    "decisions": {
        "task_id", "email_id", "source_email_id", "thread_id", "title", "description", "assignee_id", "category", "priority", "due_date",
        "deadline_at", "deal_value_inr", "company_name", "confidence", "reasoning", "evidence", "operation",
        "original_operation", "delivery_outcome", "actionability", "skip_reason", "primary_intents", "topics",
        "intent_direction", "organization_type", "alliance_subtype", "marketing_subtype", "degraded_mode", "model_name",
        "amount_mentions", "deadline_mentions", "prompt_version", "run_id", "client_batch_id", "created_at",
    },
    "threads": {
        "task_id", "source_email_id", "thread_id", "title", "description", "assignee_id", "category", "priority", "due_date",
        "deal_value_inr", "company_name", "confidence", "message_count", "update_count", "last_message_index",
        "reconciliation_status", "updated_at",
    },
    "events": {
        "task_id", "email_id", "thread_id", "event_type", "status", "attempt_count", "created_at", "confirmed_at",
        "run_id",
    },
    "feedback": {"email_id", "label", "note", "created_at"},
    "runs": {
        "run_id", "client_batch_id", "status", "received_count", "processed", "tasks_created", "tasks_updated",
        "skipped", "unchanged", "started_at", "completed_at",
    },
}

NUMERIC_ANALYTICS_FIELDS = {
    "deal_value_inr", "confidence", "message_count", "update_count", "last_message_index", "attempt_count",
    "received_count", "processed", "tasks_created", "tasks_updated", "skipped", "unchanged",
}


class AnalyticsFilter(BaseModel):
    field: AnalyticsField
    operator: FilterOperator = "eq"
    value: str | int | float | bool | list[str] | None = None

    @model_validator(mode="after")
    def value_matches_operator(self) -> "AnalyticsFilter":
        if self.operator in {"is_null", "not_null"}:
            self.value = None
        elif self.value is None:
            raise ValueError("filter value is required for this operator")
        if self.operator == "in" and not isinstance(self.value, list):
            raise ValueError("the in operator requires a list value")
        return self


class AnalyticsQuery(BaseModel):
    dataset: AnalyticsDataset
    operation: AnalyticsOperation
    filters: list[AnalyticsFilter] = Field(default_factory=list, max_length=10)
    group_by: AnalyticsField | None = None
    metric: AnalyticsField | None = None
    fields: list[AnalyticsField] = Field(default_factory=list, max_length=12)
    limit: int = Field(default=20, ge=1, le=50)

    @model_validator(mode="after")
    def query_is_allowlisted(self) -> "AnalyticsQuery":
        allowed = ANALYTICS_FIELDS[self.dataset]
        used = {item.field for item in self.filters} | set(self.fields)
        if self.group_by:
            used.add(self.group_by)
        if self.metric:
            used.add(self.metric)
        invalid = sorted(str(field) for field in used if field not in allowed)
        if invalid:
            raise ValueError(f"fields are not available for {self.dataset}: {', '.join(invalid)}")
        if self.operation == "group_count" and not self.group_by:
            raise ValueError("group_count requires group_by")
        if self.operation != "group_count" and self.group_by:
            raise ValueError("group_by is only valid for group_count")
        if self.operation == "list" and not self.fields:
            raise ValueError("list requires at least one selected field")
        if self.operation != "list" and self.fields:
            raise ValueError("selected fields are only valid for list")
        if self.operation in {"sum", "average", "minimum", "maximum"}:
            if not self.metric or self.metric not in NUMERIC_ANALYTICS_FIELDS:
                raise ValueError("numeric aggregate requires an allowlisted numeric metric")
        elif self.metric:
            raise ValueError("metric is only valid for numeric aggregate operations")
        return self


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

    @field_validator("candidate_id")
    @classmethod
    def candidate_matches(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized != LOCKED_CANDIDATE_ID:
            raise ValueError("candidate_id does not match the configured submission identity")
        return normalized


class ChatPlan(BaseModel):
    intent: ChatIntent
    categories: list[str] = Field(default_factory=list)
    skip_reasons: list[str] = Field(default_factory=list)
    priority: str | None = None
    max_confidence: float | None = Field(default=None, ge=0, le=1)
    topic: str | None = None
    subtype: str | None = None
    analytics: AnalyticsQuery | None = None

    @model_validator(mode="after")
    def analytics_matches_intent(self) -> "ChatPlan":
        if self.intent == "analytics" and self.analytics is None:
            raise ValueError("analytics intent requires an analytics query")
        if self.intent != "analytics" and self.analytics is not None:
            raise ValueError("analytics query is only valid for analytics intent")
        return self


class ChatResponse(BaseModel):
    answer: str
    supporting_data: dict[str, Any]
    scope: ChatScope
