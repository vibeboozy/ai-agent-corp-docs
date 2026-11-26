"""
ANCHOR: app.application.appeals.service
PURPOSE: Service skeleton for appeals (NotImplemented).
Dependencies: domain, persistence port
DO:
- Persist status transitions with audit
DONT:
- Call LLM or vector store from appeals service
"""

from __future__ import annotations


class AppealsService:
    """Placeholder application service — implement in later phases."""

    async def run(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise NotImplementedError("appeals service not implemented")
