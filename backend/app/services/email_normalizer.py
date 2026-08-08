from __future__ import annotations

import hashlib
import html
import json
import re
from html.parser import HTMLParser

from backend.app.domain.email_models import EmailMessage, NormalizedEmail
from backend.app.services.quote_parser import latest_reply


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.ignored = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self.ignored += 1
        elif tag in {"p", "br", "li", "div", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self.ignored:
            self.ignored -= 1
        elif tag in {"p", "li", "div", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.ignored:
            self.parts.append(data)


def html_to_text(value: str) -> str:
    if not re.search(r"<[^>]+>", value):
        return html.unescape(value)
    parser = _TextExtractor()
    parser.feed(value)
    return html.unescape("".join(parser.parts))


def normalize_email(email: EmailMessage, max_prompt_chars: int = 30_000) -> NormalizedEmail:
    body = html_to_text(email.body).replace("\r\n", "\n").replace("\r", "\n")
    body = re.sub(r"[ \t]+", " ", body)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    current = latest_reply(body) if email.message_index > 0 or email.is_reply else body
    truncated = len(current) > max_prompt_chars
    if truncated:
        current = current[:24_000] + "\n...[content truncated]...\n" + current[-6_000:]
    raw = email.model_dump(mode="json")
    digest = hashlib.sha256(
        json.dumps(raw, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    anomalies: list[str] = []
    if email.message_index == 0 and email.is_reply:
        anomalies.append("message_index_zero_marked_reply")
    if email.message_index > 0 and not email.is_reply:
        anomalies.append("reply_index_marked_non_reply")
    return NormalizedEmail(
        email=email,
        normalized_body=body,
        latest_reply_body=current,
        content_hash=digest,
        content_truncated=truncated,
        anomalies=anomalies,
        extra=email.model_extra or {},
    )
