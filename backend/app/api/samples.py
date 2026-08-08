import json
from pathlib import Path

from fastapi import APIRouter, Query

router = APIRouter(tags=["samples"])
DATA_PATH = Path(__file__).resolve().parents[3] / "data" / "inbox.json"


@router.get("/sample-emails")
def sample_emails(count: int = Query(250, ge=1, le=250)) -> dict:
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    emails = data if isinstance(data, list) else data.get("emails", [])
    return {"emails": emails[:count], "count": min(count, len(emails))}
