from fastapi import APIRouter, Depends, Query

from backend.app.dependencies import get_store
from backend.app.errors import AppError
from backend.app.repositories.store import MemoryStore
from backend.app.services.stats_service import StatsService

router = APIRouter(tags=["statistics"])


@router.get("/stats")
def stats(scope_type: str = Query("all", pattern="^(run|batch|all)$"), scope_id: str | None = None, store: MemoryStore = Depends(get_store)) -> dict:
    if scope_type != "all" and not scope_id:
        raise AppError("scope_id_required", "scope_id is required for run or batch", path="scope_id")
    return StatsService(store).get(scope_type, scope_id)
