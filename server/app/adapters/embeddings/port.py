"""
ANCHOR: app.adapters.embeddings.port
PURPOSE: EmbeddingsClient Protocol/ABC — no Stub prefix (CS-STUB-01).
Dependencies: typing.Protocol
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingsClient(Protocol):
    async def embed_dense(self, texts: list[str]) -> list[list[float]]:
        """Return dense vectors for each text."""
        ...

    async def embed_sparse(self, texts: list[str]) -> list[dict[str, float]]:
        """Return sparse weight maps for each text (token -> weight)."""
        ...
