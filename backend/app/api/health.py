from fastapi import APIRouter, Depends, Response

from backend.app.config import Settings, get_settings
from backend.app.dependencies import get_store
from backend.app.repositories.store import MemoryStore

router = APIRouter(tags=["health"])


@router.get("/health")
def health(settings: Settings = Depends(get_settings)) -> dict:
    return {"status": "alive", "app": settings.app_name, "version": "0.1.0"}


@router.get("/ready")
def ready(response: Response, settings: Settings = Depends(get_settings), store: MemoryStore = Depends(get_store)) -> dict:
    components = {
        "configuration": "ok",
        "database": "ok" if store.health() else "error",
        "migration": "ok" if store.migration_ready() else "missing",
        "task_api": "local_persistent",
        "gemini": "configured" if settings.gemini_api_key else "degraded",
    }
    is_ready = all(value not in {"error", "missing"} for value in components.values())
    if not is_ready: response.status_code = 503
    return {"status": "ready" if is_ready else "not_ready", "components": components}
