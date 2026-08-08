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
        parts = [part for part in first.get("loc", []) if part not in {"body", "query", "path"}]
        path = ""
        for part in parts:
            if isinstance(part, int):
                path += f"[{part}]"
            else:
                path += ("." if path else "") + str(part)
        path = path or None
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
        error_type = str(first.get("type") or "")
        code = "invalid_request"
        if error_type == "missing":
            code = "missing_required_field"
        elif path == "emails" and error_type in {"too_short", "list_too_short"}:
            code = "empty_batch"
        elif path == "emails" and error_type in {"too_long", "list_too_long"}:
            code = "too_many_emails"
        elif path and path.endswith("received_at"):
            code = "invalid_datetime"
        elif path and path.endswith(("from_email", "to")):
            code = "invalid_email"
        elif error_type in {"list_type", "bool_type", "string_type", "dict_type"}:
            code = "invalid_type"
        elif path and path.endswith("message_index"):
            code = "invalid_integer"
        elif "duplicate email_id" in message:
            code = "duplicate_email_id"
            path = "emails"
        elif "duplicate thread/message_index" in message:
            code = "duplicate_thread_index"
            path = "emails"
        elif error_type in {"string_too_short", "string_too_long"} or "must not be blank" in message:
            code = "invalid_string"
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "candidate_id_mismatch" if candidate_error else code,
                    "message": "candidate_id does not match the configured submission identity" if candidate_error else message,
                    "path": path,
                    "retryable": False,
                }
            },
        )
