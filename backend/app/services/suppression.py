from __future__ import annotations

import re

from backend.app.domain.enums import Actionability, SkipReason
from backend.app.domain.extraction_models import ExtractionResult
from backend.app.domain.email_models import NormalizedEmail


def deterministic_suppression(message: NormalizedEmail) -> ExtractionResult | None:
    subject = message.email.subject.lower()
    body = message.latest_reply_body.lower()
    sender = str(message.email.from_email).lower()
    joined = f"{subject}\n{body}"

    ooo_subject = any(token in subject for token in ("out of office", "automatic reply", "annual leave", "ooo"))
    ooo_body = any(token in body for token in (
        "out of office", "annual leave", "will not be forwarded", "office se bahar",
        "limited email access",
    ))
    if ooo_subject and ooo_body:
        return ExtractionResult(
            email_id=message.email.email_id,
            actionability=Actionability.NON_ACTIONABLE,
            skip_reason=SkipReason.OUT_OF_OFFICE,
            intent_direction="automated",
            topics=["auto_reply"],
            reasoning_summary="Confirmed automatic out-of-office response",
        )

    bounce_sender = "mailer-daemon" in sender or "postmaster" in sender
    bounce_text = any(token in joined for token in (
        "delivery status notification", "undeliverable", "delivery failed", "status 5.1.1",
    ))
    if bounce_sender and bounce_text:
        return ExtractionResult(
            email_id=message.email.email_id,
            actionability=Actionability.NON_ACTIONABLE,
            skip_reason=SkipReason.AUTOMATED_BOUNCE,
            intent_direction="automated",
            topics=["delivery_failure"],
            reasoning_summary="Confirmed automated delivery failure",
        )

    broadcast = any(token in joined for token in ("newsletter", "issue #", "monthly digest", "read online"))
    opt_out = any(token in body for token in ("unsubscribe", "manage preferences", "forward to a friend"))
    if broadcast and opt_out:
        return ExtractionResult(
            email_id=message.email.email_id,
            actionability=Actionability.NON_ACTIONABLE,
            skip_reason=SkipReason.NEWSLETTER,
            intent_direction="broadcast",
            topics=["newsletter"],
            reasoning_summary="Broadcast newsletter with opt-out signals",
        )

    vendor_phrases = (
        "we offer content marketing", "secure pr backlinks", "verified leads",
        "appointment-setting services", "seo audit subscription", "offshore development shop",
        "book a sales call", "not ranking on page one", "buy our placement package",
    )
    direct_sale = sum(1 for phrase in vendor_phrases if phrase in body)
    if direct_sale >= 1 and any(token in body for token in ("we offer", "we sell", "buy our", "book", "pricing", "subscription")):
        return ExtractionResult(
            email_id=message.email.email_id,
            actionability=Actionability.NON_ACTIONABLE,
            skip_reason=SkipReason.VENDOR_SPAM,
            intent_direction="selling_to_us",
            topics=["unsolicited_vendor_offer"],
            reasoning_summary="High-confidence unsolicited vendor offer selling services to us",
        )

    if re.fullmatch(r"(?is)\s*(thanks|thank you)[,! .]*(received|noted)?[.! ]*", message.latest_reply_body):
        return ExtractionResult(
            email_id=message.email.email_id,
            actionability=Actionability.NON_ACTIONABLE,
            intent_direction="unclear",
            topics=["acknowledgement"],
            reasoning_summary="Acknowledgement contains no new actionable facts",
        )
    return None
