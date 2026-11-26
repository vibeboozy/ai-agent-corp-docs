"""
ANCHOR: app.adapters.stubs.vectorstore
PURPOSE: StubVectorStore — deterministic fixture KB search/upsert (ANC-STUB-02).
Dependencies: app.adapters.vectorstore.port.VectorStore; stubs.fixtures
DO:
- Keep offline and side-effect free (except in-process learning upserts)
DONT:
- Perform real network I/O
"""

from __future__ import annotations

from typing import Any

from app.adapters.stubs.fixtures import SHARED_FIXTURE_KB, FixtureChunk, FixtureKB
from app.adapters.vectorstore.port import VectorStore


class StubVectorStore:
    """Keyword-scored fixture vector store."""

    def __init__(self, kb: FixtureKB | None = None) -> None:
        self._kb = kb or SHARED_FIXTURE_KB

    async def ping(self) -> bool:
        return True

    async def search(
        self,
        query: str,
        *,
        limit: int = 5,
        dense_vector: list[float] | None = None,
    ) -> list[dict[str, Any]]:
        _ = dense_vector
        hits = self._kb.search(query, limit=limit)
        return [
            {
                "document_id": chunk.document_id,
                "chunk_id": chunk.chunk_id,
                "text": chunk.text,
                "score": score,
                "document_title": chunk.document_title,
                "locator": chunk.locator,
                "source": chunk.source,
                "metadata": chunk.metadata,
            }
            for chunk, score in hits
        ]

    async def upsert(self, chunks: list[dict[str, Any]]) -> None:
        for raw in chunks:
            keywords = raw.get("keywords") or []
            if not keywords and raw.get("text"):
                keywords = [t for t in str(raw["text"]).lower().split() if len(t) > 4][:12]
            self._kb.upsert(
                FixtureChunk(
                    document_id=str(raw["document_id"]),
                    chunk_id=str(raw["chunk_id"]),
                    text=str(raw["text"]),
                    document_title=str(raw.get("document_title") or "Learned answer"),
                    keywords=list(keywords),
                    locator=raw.get("locator"),
                    source=str(raw.get("source") or "learned"),
                    metadata=dict(raw.get("metadata") or {}),
                )
            )


_: VectorStore = StubVectorStore()  # type: ignore[assignment]
