"""
ANCHOR: app.application.quality_escalation.service
PURPOSE: Service skeleton for quality_escalation (NotImplemented).
Dependencies: escalation adapter, persistence, appeals
CRITICAL: Unsupported after clarify → escalate, do not invent (ANC-ESC-01).
DO:
- Treat escalation as successful business path
DONT:
- Return HTTP 500 for grounding failure alone
"""

from __future__ import annotations


class QualityEscalationService:
    """Placeholder application service — implement in later phases."""

    async def run(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise NotImplementedError("quality_escalation service not implemented")
