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
        Settings(app_env="production", supabase_db_url="", gemini_api_key="")


def test_production_accepts_the_single_configured_project() -> None:
    settings = Settings(
        app_env="production",
        supabase_db_url="postgresql://postgres.projectref@pooler.example.com:5432/postgres",
        gemini_api_key="test-key",
        frontend_origins="https://app.example.com",
        production_supabase_host="pooler.example.com",
        production_supabase_project_ref="projectref",
    )
    assert settings.database_project_ref == "projectref"


def test_production_rejects_a_different_project() -> None:
    with pytest.raises(ValidationError, match="does not match"):
        Settings(
            app_env="production",
            supabase_db_url="postgresql://postgres.wrongref@pooler.example.com:5432/postgres",
            gemini_api_key="test-key",
            frontend_origins="https://app.example.com",
            production_supabase_host="pooler.example.com",
            production_supabase_project_ref="projectref",
        )


def test_test_environment_blocks_production_project_by_default() -> None:
    with pytest.raises(ValidationError, match="tests may not target"):
        Settings(
            app_env="test",
            supabase_db_url="postgresql://postgres.projectref@pooler.example.com:5432/postgres",
            production_supabase_host="pooler.example.com",
        )


def test_scoped_integration_test_can_explicitly_opt_in_to_production_project() -> None:
    settings = Settings(
        app_env="test",
        supabase_db_url="postgresql://postgres.projectref@pooler.example.com:5432/postgres",
        production_supabase_host="pooler.example.com",
        allow_production_test_database=True,
    )
    assert settings.allow_production_test_database is True
