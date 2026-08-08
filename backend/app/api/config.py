from fastapi import APIRouter, Depends

from backend.app.config import Settings, get_settings

router = APIRouter(tags=["configuration"])


@router.get("/config")
def public_config(settings: Settings = Depends(get_settings)) -> dict:
    return {"app_name": settings.app_name, "candidate_id": settings.candidate_id, "max_ingest_emails": settings.ingest_max_emails}
