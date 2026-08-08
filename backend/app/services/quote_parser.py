from __future__ import annotations

import re


QUOTE_MARKERS = (
    re.compile(r"(?im)^on .+ wrote:\s*$"),
    re.compile(r"(?im)^on the earlier message:\s*$"),
    re.compile(r"(?im)^-{2,}\s*original message\s*-{2,}\s*$"),
    re.compile(r"(?im)^from:\s+.+$"),
)


FORWARD_HINT = re.compile(
    r"(?is)(forwarded message|begin forwarded message|forwarding (?:this|the)|\bfwd:)"
)


def latest_reply(text: str) -> str:
    """Return current reply text without deleting a forwarded message body."""
    candidates: list[int] = []
    for pattern in QUOTE_MARKERS:
        match = pattern.search(text)
        if match:
            # A human may add a short instruction above a forwarded email. In that
            # case the forwarded body is the actionable evidence, not quoted history.
            # Preserve it when the text immediately before the header says it is a
            # forward; normal reply chains are still split at the same markers.
            prefix = text[: match.start()]
            if FORWARD_HINT.search(prefix[-300:]):
                continue
            # A message beginning with From:/Sent: is usually a forwarded message and
            # remains actionable; only split when meaningful current text precedes it.
            if match.start() > 0:
                candidates.append(match.start())
    if candidates:
        return text[: min(candidates)].strip()
    lines = [line for line in text.splitlines() if not line.lstrip().startswith(">")]
    return "\n".join(lines).strip()
