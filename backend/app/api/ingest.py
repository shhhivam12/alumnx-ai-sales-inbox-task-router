from fastapi import APIRouter, Depends

from backend.app.dependencies import get_ingestion_service
from backend.app.domain.email_models import IngestRequest, IngestResponse
from backend.app.services.ingestion_service import IngestionService

router = APIRouter(tags=["ingestion"])


@router.post("/ingest", response_model=IngestResponse)
def ingest(payload: IngestRequest, service: IngestionService = Depends(get_ingestion_service)) -> IngestResponse:
    return service.ingest(payload)
