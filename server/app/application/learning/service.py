"""
ANCHOR: app.application.learning.service
PURPOSE: Service skeleton for learning (NotImplemented).
Dependencies: persistence, ingest, appeals
CRITICAL: Missing KB + officer reply MUST update KB (ANC-LEARN-01).
DO:
- Log all learning events
DONT:
- Silent message append without learning side-effects
"""

from __future__ import annotations


class LearningService:
    """Placeholder application service — implement in later phases."""

    async def run(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise NotImplementedError("learning service not implemented")
