"""
ANCHOR: app.application.retrieval.service
PURPOSE: Hybrid retrieval via embeddings + vectorstore ports (stub-friendly).
Dependencies: embeddings port, vectorstore port
DO:
- Prefer latest effective docs when configured
DONT:
- Return answers — retrieval only yields candidates
"""

from __future__ import annotations

from typing import Any

from app.adapters.embeddings.port import EmbeddingsClient
from app.adapters.vectorstore.port import VectorStore


class RetrievalService:
    def __init__(
        self,
        *,
        embeddings: EmbeddingsClient,
        vectorstore: VectorStore,
        prefetch: int = 50,
        prefer_latest: bool = True,
    ) -> None:
        self._embeddings = embeddings
        self._vectorstore = vectorstore
        self._prefetch = prefetch
        self._prefer_latest = prefer_latest

    async def retrieve(self, query: str, *, limit: int = 5) -> list[dict[str, Any]]:
        vectors = await self._embeddings.embed_dense([query])
        dense = vectors[0] if vectors else None
        hits = await self._vectorstore.search(
            query, limit=min(limit, self._prefetch), dense_vector=dense
        )
        if self._prefer_latest:
            # Learned chunks (source=learned) win ties for continuous-learning demos.
            hits.sort(
                key=lambda h: (
                    1 if h.get("source") == "learned" else 0,
                    float(h.get("score") or 0.0),
                ),
                reverse=True,
            )
        return hits[:limit]
