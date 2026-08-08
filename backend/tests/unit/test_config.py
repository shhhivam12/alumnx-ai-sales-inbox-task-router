import pytest
from pydantic import ValidationError

from backend.app.config import Settings


def test_public_supabase_url_is_rejected_with_clear_error() -> None:
    with pytest.raises(ValidationError, match="PostgreSQL connection string"):
        Settings(supabase_db_url="https://project.supabase.co")


def test_database_url_requires_tls_automatically() -> None:
    settings = Settings(supabase_db_url="postgresql://postgres@db.example.com:5432/postgres")
    assert settings.supabase_db_url.endswith("sslmode=require")


def test_production_requires_live_dependencies() -> None:
    with pytest.raises(ValidationError):
        Settings(app_env="production", supabase_db_url="", gemini_api_key="", task_api_mode="fake")
