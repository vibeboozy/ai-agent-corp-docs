"""
ANCHOR: app.application.grounding.service
PURPOSE: Service skeleton for grounding (NotImplemented).
Dependencies: domain ChunkCitation; optional llm port for draft assist
CRITICAL: Final answers MUST be chunk-supported (ANC-GROUND-01/02).
DO:
- Refuse or escalate unsupported claims
DONT:
- Treat LLM draft as sole source of truth
"""

from __future__ import annotations


class GroundingService:
    """Placeholder application service — implement in later phases."""

    async def run(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise NotImplementedError("grounding service not implemented")
