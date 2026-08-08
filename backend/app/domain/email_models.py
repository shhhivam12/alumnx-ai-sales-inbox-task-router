from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StrictBool, field_validator, model_validator

from backend.app.config import LOCKED_CANDIDATE_ID


class EmailMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    email_id: str = Field(min_length=1, max_length=128)
    thread_id: str = Field(min_length=1, max_length=128)
    message_index: int = Field(strict=True, ge=0)
    from_name: str = Field(max_length=256)
    from_email: EmailStr
    to: EmailStr
    cc: list[EmailStr] = Field(max_length=100)
    subject: str = Field(max_length=1000)
    body: str = Field(max_length=250_000)
    received_at: datetime
    attachments: list[str] = Field(max_length=50)
    is_reply: StrictBool

    @field_validator("email_id", "thread_id")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value.strip()

    @field_validator("received_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timezone-aware ISO-8601 timestamp required")
        return value

    @field_validator("attachments")
    @classmethod
    def attachment_lengths(cls, value: list[str]) -> list[str]:
        if any(len(item) > 255 for item in value):
            raise ValueError("attachment names must be at most 255 characters")
        return value


class IngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    client_batch_id: UUID | None = None
    source: str = "api"
    emails: list[EmailMessage] = Field(min_length=1, max_length=100)

    @field_validator("candidate_id")
    @classmethod
    def candidate_matches(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized != LOCKED_CANDIDATE_ID:
            raise ValueError("candidate_id does not match the configured submission identity")
        return normalized

    @field_validator("source")
    @classmethod
    def source_allowed(cls, value: str) -> str:
        if value not in {"pasted", "uploaded", "generated", "grader", "api"}:
            raise ValueError("invalid source")
        return value

    @model_validator(mode="after")
    def unique_keys(self) -> "IngestRequest":
        email_ids: set[str] = set()
        thread_indexes: set[tuple[str, int]] = set()
        for email in self.emails:
            if email.email_id in email_ids:
                raise ValueError(f"duplicate email_id: {email.email_id}")
            email_ids.add(email.email_id)
            key = (email.thread_id, email.message_index)
            if key in thread_indexes:
                raise ValueError(f"duplicate thread/message_index: {email.thread_id}/{email.message_index}")
            thread_indexes.add(key)
        return self


class IngestError(BaseModel):
    email_id: str | None = None
    thread_id: str | None = None
    stage: str
    code: str
    message: str
    retryable: bool = False


class IngestResponse(BaseModel):
    run_id: UUID
    processed: int
    tasks_created: int
    tasks_updated: int
    skipped: int
    unchanged: int
    errors: list[IngestError] = Field(default_factory=list)


class NormalizedEmail(BaseModel):
    email: EmailMessage
    normalized_body: str
    latest_reply_body: str
    content_hash: str
    content_truncated: bool = False
    anomalies: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)
