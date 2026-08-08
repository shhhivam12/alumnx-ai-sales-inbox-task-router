from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.api import api_router
from backend.app.config import get_settings
from backend.app.errors import install_error_handlers
from backend.app.logging_config import configure_logging

settings = get_settings()
configure_logging(settings.log_level)
app = FastAPI(title=settings.app_name, version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=False, allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Content-Type"])


@app.middleware("http")
async def request_size_limit(request: Request, call_next):
    if request.method == "POST" and int(request.headers.get("content-length", "0") or 0) > settings.ingest_max_request_bytes:
        return JSONResponse(status_code=413, content={"error": {"code": "request_too_large", "message": "request exceeds 25 MiB", "path": None, "retryable": False}})
    return await call_next(request)


install_error_handlers(app)
app.include_router(api_router)
