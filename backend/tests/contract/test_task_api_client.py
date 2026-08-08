import json

import httpx
import pytest
import respx

from backend.app.config import Settings
from backend.app.domain.enums import AssigneeId, Category, Priority
from backend.app.domain.task_models import TaskPatch, TaskPayload
from backend.app.errors import AppError
from backend.app.services.task_api_client import LiveTaskApi


def settings() -> Settings:
    return Settings(
        supabase_db_url="", task_api_mode="live", task_api_base_url="https://tasks.example.test",
        task_api_max_retries=2,
    )


def payload() -> TaskPayload:
    return TaskPayload(
        candidate_id="mahendrushivam123@gmail.com", source_email_id="email-1", thread_id="thread-1",
        title="Demo", description="Buyer requested a demo", assignee_id=AssigneeId.ROHIT,
        category=Category.SMB_ENQUIRY, priority=Priority.MEDIUM, due_date=None,
        deal_value_inr=None, company_name=None, confidence=.84,
    )


@respx.mock
def test_exact_create_and_patch_contract() -> None:
    create = respx.post("https://tasks.example.test/tasks").mock(
        return_value=httpx.Response(201, json={"task_id": "tsk_1", "candidate_id": "mahendrushivam123@gmail.com", "source_email_id": "email-1"})
    )
    patch = respx.patch("https://tasks.example.test/tasks/tsk_1").mock(
        return_value=httpx.Response(200, json=payload().model_dump(mode="json") | {"task_id": "tsk_1", "priority": "high"})
    )
    client = LiveTaskApi(settings())
    created = client.create_task(payload())
    assert created["task_id"] == "tsk_1"
    assert created["category"] == "smb_enquiry"
    assert json.loads(create.calls[0].request.content)["candidate_id"] == "mahendrushivam123@gmail.com"
    updated = client.patch_task("tsk_1", TaskPatch(priority=Priority.HIGH))
    assert updated["priority"] == "high"
    assert json.loads(patch.calls[0].request.content) == {"priority": "high"}


@respx.mock
def test_list_always_supplies_locked_candidate() -> None:
    route = respx.get("https://tasks.example.test/tasks").mock(return_value=httpx.Response(200, json=[]))
    LiveTaskApi(settings()).list_tasks(thread_id="thread-1")
    request = route.calls[0].request
    assert request.url.params["candidate_id"] == "mahendrushivam123@gmail.com"
    assert request.url.params["thread_id"] == "thread-1"


@respx.mock
def test_ambiguous_post_is_not_retried() -> None:
    route = respx.post("https://tasks.example.test/tasks").mock(side_effect=httpx.ReadTimeout("uncertain"))
    with pytest.raises(AppError, match="uncertain"):
        LiveTaskApi(settings()).create_task(payload())
    assert route.call_count == 1
