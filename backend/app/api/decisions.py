from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend.app.dependencies import get_store
from backend.app.repositories.store import MemoryStore

router = APIRouter(tags=["decisions"])


class FeedbackRequest(BaseModel):
    label: Literal["correct", "misrouted", "missed", "spurious"]
    note: str | None = Field(default=None, max_length=2000)


@router.get("/batches/{client_batch_id}/decisions")
def batch_decisions(client_batch_id: UUID, store: MemoryStore = Depends(get_store)) -> dict:
    rows = store.list_decisions("batch", str(client_batch_id))
    return {"items": rows, "total": len(rows)}


@router.post("/decisions/{email_id}/feedback")
def feedback(email_id: str, payload: FeedbackRequest, store: MemoryStore = Depends(get_store)) -> dict:
    return store.set_feedback(email_id, payload.label, payload.note)
