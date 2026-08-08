from __future__ import annotations

import time
from copy import deepcopy
from threading import RLock
from typing import Any, Protocol
from uuid import uuid4

import httpx

from backend.app.config import LOCKED_CANDIDATE_ID, Settings
from backend.app.errors import AppError
from backend.app.domain.task_models import TaskPatch, TaskPayload


class TaskApi(Protocol):
    def list_tasks(self, *, thread_id: str | None = None, source_email_id: str | None = None) -> list[dict[str, Any]]: ...
    def create_task(self, payload: TaskPayload) -> dict[str, Any]: ...
    def patch_task(self, task_id: str, patch: TaskPatch) -> dict[str, Any]: ...
    def get_task(self, task_id: str) -> dict[str, Any] | None: ...


class FakeTaskApi:
    def __init__(self) -> None:
        self._tasks: dict[str, dict[str, Any]] = {}
        self._lock = RLock()

    def list_tasks(self, *, thread_id: str | None = None, source_email_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            values = self._tasks.values()
            return [deepcopy(item) for item in values if (not thread_id or item["thread_id"] == thread_id) and (not source_email_id or item["source_email_id"] == source_email_id)]

    def create_task(self, payload: TaskPayload) -> dict[str, Any]:
        with self._lock:
            task = payload.model_dump(mode="json") | {"task_id": f"tsk_fake_{uuid4().hex[:12]}"}
            self._tasks[task["task_id"]] = task
            return deepcopy(task)

    def patch_task(self, task_id: str, patch: TaskPatch) -> dict[str, Any]:
        with self._lock:
            if task_id not in self._tasks:
                raise AppError("task_not_found", "remote task was not found", status_code=502)
            self._tasks[task_id].update(patch.model_dump(mode="json", exclude_unset=True))
            return deepcopy(self._tasks[task_id])

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            return deepcopy(self._tasks.get(task_id))


class LiveTaskApi:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = httpx.Client(
            base_url=settings.task_api_base_url.rstrip("/"),
            timeout=httpx.Timeout(settings.task_api_read_timeout_seconds, connect=settings.task_api_connect_timeout_seconds),
        )

    def _request(self, method: str, path: str, *, allow_retry: bool = True, **kwargs: Any) -> httpx.Response:
        retryable = {429, 500, 502, 503, 504}
        last: Exception | None = None
        max_retries = self.settings.task_api_max_retries if allow_retry else 0
        for attempt in range(max_retries + 1):
            try:
                response = self.client.request(method, path, **kwargs)
                if response.status_code not in retryable:
                    if response.status_code >= 400:
                        raise AppError("task_api_error", f"Task API rejected request ({response.status_code}): {response.text[:500]}", status_code=502)
                    return response
                last = RuntimeError(f"Task API returned {response.status_code}")
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else min(0.25 * 2**attempt, 3)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last = exc
                delay = min(0.25 * 2**attempt, 3)
            if attempt < max_retries:
                time.sleep(delay)
        raise AppError("task_api_unavailable", str(last or "Task API unavailable"), status_code=502, retryable=True)

    def list_tasks(self, *, thread_id: str | None = None, source_email_id: str | None = None) -> list[dict[str, Any]]:
        params = {"candidate_id": LOCKED_CANDIDATE_ID}
        if thread_id:
            params["thread_id"] = thread_id
        if source_email_id:
            params["source_email_id"] = source_email_id
        body = self._request("GET", "/tasks", params=params).json()
        return body if isinstance(body, list) else body.get("items", body.get("tasks", []))

    def create_task(self, payload: TaskPayload) -> dict[str, Any]:
        # A POST timeout is ambiguous. Reconciliation queries by thread/source
        # before any later delivery can attempt another create.
        fields = payload.model_dump(mode="json")
        response = self._request("POST", "/tasks", allow_retry=False, json=fields).json()
        return fields | response

    def patch_task(self, task_id: str, patch: TaskPatch) -> dict[str, Any]:
        return self._request("PATCH", f"/tasks/{task_id}", json=patch.model_dump(mode="json", exclude_unset=True)).json()

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        response = self.client.get(f"/tasks/{task_id}", params={"candidate_id": LOCKED_CANDIDATE_ID})
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise AppError("task_api_error", f"Task API returned {response.status_code}", status_code=502)
        return response.json()


def build_task_api(settings: Settings) -> TaskApi:
    return LiveTaskApi(settings) if settings.task_api_mode == "live" else FakeTaskApi()
