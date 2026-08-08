from __future__ import annotations

from backend.app.domain.enums import AssigneeId
from backend.app.domain.extraction_models import ExtractionResult


def calculate_confidence(
    extraction: ExtractionResult,
    assignee: AssigneeId | None,
    *,
    hard_rule: bool = False,
    company_from_domain: bool = False,
    degraded: bool = False,
) -> float:
    if extraction.skip_reason:
        base = 0.96
    elif assignee == AssigneeId.TRIAGE:
        base = 0.45
    elif hard_rule:
        base = 0.92
    elif any(amount.role == "deal_budget" for amount in extraction.amounts):
        base = 0.88
    elif assignee == AssigneeId.ROHIT:
        base = 0.80
    else:
        base = 0.84
    evidence_count = len(extraction.amounts) + len(extraction.deadlines) + bool(extraction.organization_evidence)
    if evidence_count >= 2:
        base += 0.03
    if assignee and assignee in extraction.owner_candidates:
        base += 0.02
    if company_from_domain:
        base -= 0.08
    if extraction.content_truncated:
        base -= 0.08
    if extraction.multiple_material_asks:
        base -= 0.18
    if degraded:
        base = min(base - 0.20, 0.65 if hard_rule else 0.30)
    base = min(0.98, max(0.05, base))
    if assignee == AssigneeId.TRIAGE:
        base = min(0.54, max(0.30, base))
    return round(base, 3)
