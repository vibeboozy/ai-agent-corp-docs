"""
ANCHOR: app.application.retrieval.service
PURPOSE: Service skeleton for retrieval (NotImplemented).
Dependencies: embeddings port, vectorstore port, optional llm for rerank
DO:
- Prefer latest effective docs when configured
DONT:
- Return answers — retrieval only yields candidates
"""

from __future__ import annotations


class RetrievalService:
    """Placeholder application service — implement in later phases."""

    async def run(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise NotImplementedError("retrieval service not implemented")
