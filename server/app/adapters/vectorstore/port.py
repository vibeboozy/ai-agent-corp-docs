"""
ANCHOR: app.adapters.vectorstore.port
PURPOSE: VectorStore Protocol/ABC — no Stub prefix (CS-STUB-01).
Dependencies: typing.Protocol
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class VectorStore(Protocol):
    async def ping(self) -> bool:
        """Connectivity probe — True when the store is reachable."""
        ...

    async def search(
        self,
        query: str,
        *,
        limit: int = 5,
        dense_vector: list[float] | None = None,
    ) -> list[dict[str, Any]]:
        """Return candidate chunks: document_id, chunk_id, text, score, …"""
        ...

    async def upsert(self, chunks: list[dict[str, Any]]) -> None:
        """Upsert chunks into the active collection / stub KB."""
        ...
