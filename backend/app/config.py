from __future__ import annotations

from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


LOCKED_CANDIDATE_ID = "mahendrushivam123@gmail.com"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_name: str = "Alumnx AI Sales inbox task router"
    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"

    candidate_id: str = LOCKED_CANDIDATE_ID
    frontend_origins: str = "http://localhost:5173"

    supabase_db_url: str = ""
    supabase_migration_db_url: str = ""
    development_supabase_host: str = ""
    production_supabase_host: str = ""
    development_supabase_project_ref: str = ""
    production_supabase_project_ref: str = ""
    db_pool_min_size: int = Field(default=1, ge=0, le=5)
    db_pool_max_size: int = Field(default=5, ge=1, le=20)
    db_pool_recycle_seconds: int = Field(default=300, ge=30)

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_temperature: float = Field(default=0.1, ge=0, le=1)
    gemini_batch_size: int = Field(default=5, ge=1, le=5)
    gemini_requests_per_minute: int = Field(default=5, ge=1)
    gemini_max_concurrency: int = Field(default=1, ge=1, le=4)
    gemini_timeout_seconds: float = Field(default=60, gt=0)
    gemini_max_retries: int = Field(default=5, ge=0, le=10)
    gemini_max_output_tokens: int = Field(default=8192, ge=512)

    ingest_max_emails: int = Field(default=100, ge=1, le=100)
    ingest_max_request_bytes: int = Field(default=26_214_400, ge=1_048_576)
    email_body_max_chars: int = Field(default=250_000, ge=10_000)
    normalized_prompt_max_chars: int = Field(default=30_000, ge=5_000)

    routing_prompt_version: str = "routing-v1"
    chat_prompt_version: str = "chat-v1"

    @field_validator("candidate_id")
    @classmethod
    def normalize_candidate(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized != LOCKED_CANDIDATE_ID:
            raise ValueError(f"candidate_id must be {LOCKED_CANDIDATE_ID}")
        return normalized

    @property
    def cors_origins(self) -> list[str]:
        return [item.strip() for item in self.frontend_origins.split(",") if item.strip()]

    @property
    def database_host(self) -> str:
        return (urlparse(self.supabase_db_url).hostname or "").lower()

    @property
    def database_project_ref(self) -> str:
        username = urlparse(self.supabase_db_url).username or ""
        return username.rsplit(".", 1)[-1].lower() if "." in username else ""

    @model_validator(mode="after")
    def validate_environment(self) -> "Settings":
        if self.db_pool_min_size > self.db_pool_max_size:
            raise ValueError("DB_POOL_MIN_SIZE cannot exceed DB_POOL_MAX_SIZE")
        if self.supabase_db_url:
            parsed = urlparse(self.supabase_db_url)
            if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname or not parsed.username:
                raise ValueError(
                    "SUPABASE_DB_URL must be a PostgreSQL connection string, not the public Supabase project URL"
                )
            if "sslmode=" not in self.supabase_db_url:
                separator = "&" if "?" in self.supabase_db_url else "?"
                self.supabase_db_url += f"{separator}sslmode=require"
        if self.supabase_migration_db_url:
            migration = urlparse(self.supabase_migration_db_url)
            if migration.scheme not in {"postgres", "postgresql"} or not migration.hostname or not migration.username:
                raise ValueError("SUPABASE_MIGRATION_DB_URL must be a PostgreSQL connection string")
        if self.app_env == "production":
            if not self.supabase_db_url:
                raise ValueError("SUPABASE_DB_URL is required in production")
            if not self.gemini_api_key:
                raise ValueError("GEMINI_API_KEY is required in production")
            if not self.cors_origins or "*" in self.cors_origins:
                raise ValueError("production CORS must contain exact origins")
            if self.production_supabase_host and self.database_host != self.production_supabase_host.lower():
                raise ValueError("production database host does not match the configured production host")
            if self.development_supabase_host and self.database_host == self.development_supabase_host.lower():
                raise ValueError("production may not point at the development Supabase project")
            if not self.production_supabase_project_ref:
                raise ValueError("PRODUCTION_SUPABASE_PROJECT_REF is required in production")
            if self.database_project_ref != self.production_supabase_project_ref.lower():
                raise ValueError("production database does not match PRODUCTION_SUPABASE_PROJECT_REF")
            if self.development_supabase_project_ref and self.database_project_ref == self.development_supabase_project_ref.lower():
                raise ValueError("production may not point at the development Supabase project")
        if self.app_env == "test" and self.production_supabase_host and self.database_host == self.production_supabase_host.lower():
            raise ValueError("tests may not target the production Supabase project")
        if self.app_env == "test" and self.production_supabase_project_ref and self.database_project_ref == self.production_supabase_project_ref.lower():
            raise ValueError("tests may not target the production Supabase project")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
