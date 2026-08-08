from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.app.domain.enums import AssigneeId, Category, Priority


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        path: str | None = None,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.path = path
        self.retryable = retryable
        self.details = details or {}

    def body(self) -> dict[str, Any]:
        error: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "path": self.path,
            "retryable": self.retryable,
        }
        error.update(self.details)
        return {"error": error}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.body())

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        path = ".".join(str(part) for part in first.get("loc", []) if part != "body") or None
        message = first.get("msg", "Request validation failed")
        candidate_error = path == "candidate_id" and "submission identity" in message
        enum_values = {
            "assignee_id": [item.value for item in AssigneeId],
            "category": [item.value for item in Category],
            "priority": [item.value for item in Priority],
        }
        if request.url.path.startswith("/tasks") and path in enum_values and first.get("type") == "enum":
            return JSONResponse(
                status_code=400,
                content={
                    "error": "invalid_enum_value",
                    "field": path,
                    "received": first.get("input"),
                    "allowed": enum_values[path],
                },
            )
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "candidate_id_mismatch" if candidate_error else "invalid_request",
                    "message": "candidate_id does not match the configured submission identity" if candidate_error else message,
                    "path": path,
                    "retryable": False,
                }
            },
        )
