from __future__ import annotations

from functools import lru_cache

from backend.app.config import get_settings
from backend.app.repositories.store import MemoryStore
from backend.app.repositories.postgres_store import PostgresStore
from backend.app.db.pool import DatabasePool
from backend.app.services.gemini_extractor import GeminiExtractor
from backend.app.services.ingestion_service import IngestionService
from backend.app.services.reconciler import Reconciler
from backend.app.services.task_api_client import TaskApi, build_task_api


@lru_cache
def get_store() -> MemoryStore | PostgresStore:
    settings = get_settings()
    return PostgresStore(DatabasePool(settings)) if settings.supabase_db_url else MemoryStore()


@lru_cache
def get_task_api() -> TaskApi:
    return build_task_api(get_settings())


@lru_cache
def get_ingestion_service() -> IngestionService:
    settings, store, task_api = get_settings(), get_store(), get_task_api()
    return IngestionService(settings, store, GeminiExtractor(settings), Reconciler(store, task_api))
