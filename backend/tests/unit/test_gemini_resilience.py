import json
from datetime import datetime, timezone
from types import SimpleNamespace

from backend.app.config import Settings
from backend.app.domain.email_models import EmailMessage
from backend.app.services.email_normalizer import normalize_email
from backend.app.services.gemini_extractor import GeminiExtractor


def messages():
    rows = []
    for index in range(2):
        email = EmailMessage(
            email_id=f"gemini-{index}", thread_id=f"thread-{index}", message_index=0,
            from_name="Buyer", from_email="buyer@example.com", to="sales@example.com", cc=[],
            subject="Demo", body="Please arrange a product demo.",
            received_at=datetime(2026, 8, 9, tzinfo=timezone.utc), attachments=[], is_reply=False,
        )
        rows.append(normalize_email(email))
    return rows


def result(email_id: str) -> dict:
    return {"email_id": email_id, "actionability": "actionable", "primary_intents": ["demo_request"], "reasoning_summary": "demo request"}


def extractor() -> GeminiExtractor:
    settings = Settings(
        supabase_db_url="", gemini_api_key="test-key", gemini_max_retries=0,
        gemini_requests_per_minute=1_000_000,
    )
    return GeminiExtractor(settings)


def prompt_ids(contents: str) -> list[str]:
    items = json.loads(contents.split("EMAILS:\n", 1)[1])
    return [item["email_id"] for item in items]


def test_missing_batch_item_retries_only_that_item() -> None:
    target = extractor()
    calls = []

    def generate_content(**kwargs):
        ids = prompt_ids(kwargs["contents"]); calls.append(ids)
        returned = ids[:1]
        return SimpleNamespace(text=json.dumps({"results": [result(email_id) for email_id in returned]}))

    target._client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    output = target.extract_many(messages())
    assert [item.email_id for item in output] == ["gemini-0", "gemini-1"]
    assert calls == [["gemini-0", "gemini-1"], ["gemini-1"]]


def test_malformed_batch_splits_and_total_failure_degrades() -> None:
    target = extractor()

    def split_response(**kwargs):
        ids = prompt_ids(kwargs["contents"])
        if len(ids) > 1:
            return SimpleNamespace(text="not-json")
        return SimpleNamespace(text=json.dumps({"results": [result(ids[0])]}))

    target._client = SimpleNamespace(models=SimpleNamespace(generate_content=split_response))
    assert all(not item.reasoning_summary.startswith("Degraded") for item in target.extract_many(messages()))

    failing = extractor()
    failing._client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **_: (_ for _ in ()).throw(RuntimeError("down"))))
    output = failing.extract_many(messages())
    assert all(item.reasoning_summary.startswith("Degraded deterministic extraction") for item in output)
