from __future__ import annotations

import re


QUOTE_MARKERS = (
    re.compile(r"(?im)^on .+ wrote:\s*$"),
    re.compile(r"(?im)^-{2,}\s*original message\s*-{2,}\s*$"),
    re.compile(r"(?im)^from:\s+.+$"),
)


def latest_reply(text: str) -> str:
    """Return current reply text without deleting a forwarded message body."""
    candidates: list[int] = []
    for pattern in QUOTE_MARKERS:
        match = pattern.search(text)
        if match:
            # A message beginning with From:/Sent: is usually a forwarded message and
            # remains actionable; only split when meaningful current text precedes it.
            if match.start() > 20:
                candidates.append(match.start())
    if candidates:
        return text[: min(candidates)].strip()
    lines = [line for line in text.splitlines() if not line.lstrip().startswith(">")]
    return "\n".join(lines).strip()
