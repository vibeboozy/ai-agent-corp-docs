"""
ANCHOR: app.adapters.embeddings.port
PURPOSE: EmbeddingsClient Protocol/ABC for dense/sparse vectors.
Dependencies: typing.Protocol
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingsClient(Protocol):
    async def ping(self) -> bool:
        """Connectivity probe — True when the provider is reachable."""
        ...

    async def embed_dense(self, texts: list[str]) -> list[list[float]]:
        """Return dense vectors for each text."""
        ...

    async def embed_sparse(self, texts: list[str]) -> list[dict[str, float]]:
        """Return sparse weight maps for each text (token -> weight)."""
        ...
