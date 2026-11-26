"""
ANCHOR: tests.application.test_retrieval_rerank
PURPOSE: Offline RERANK_MODE=none|llm before answer context.
Dependencies: RetrievalService + Fake embeddings/vectorstore/LLM
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.application.retrieval.service import RetrievalService


class _Emb:
    async def embed_dense(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] for _ in texts]

    async def embed_sparse(self, texts: list[str]) -> list[dict[str, float]]:
        return [{"q": 1.0} for _ in texts]


class _VS:
    def __init__(self, hits: list[dict[str, Any]]) -> None:
        self.hits = hits
        self.last_limit: int | None = None

    async def search(
        self,
        query: str,
        *,
        limit: int = 5,
        dense_vector: list[float] | None = None,
        sparse_vector: dict[str, float] | None = None,
    ) -> list[dict[str, Any]]:
        _ = (dense_vector, sparse_vector)
        self.last_limit = limit
        return list(self.hits)


@pytest.mark.asyncio
async def test_rerank_mode_none_returns_top_k() -> None:
    hits = [
        {"document_id": "d1", "chunk_id": "c1", "text": "a", "score": 0.9, "source": "ingest"},
        {"document_id": "d1", "chunk_id": "c2", "text": "b", "score": 0.8, "source": "ingest"},
        {"document_id": "d2", "chunk_id": "c3", "text": "c", "score": 0.7, "source": "ingest"},
    ]
    svc = RetrievalService(
        embeddings=_Emb(),
        vectorstore=_VS(hits),
        prefetch=50,
        rerank_mode="none",
        rerank_top_k=2,
    )
    out = await svc.retrieve("q", limit=5)
    assert len(out) == 2
    assert out[0]["chunk_id"] == "c1"


@pytest.mark.asyncio
async def test_rerank_mode_llm_reorders_and_caps_per_doc() -> None:
    hits = [
        {
            "document_id": "d1",
            "chunk_id": "c1",
            "text": "unrelated",
            "score": 0.99,
            "source": "ingest",
        },
        {
            "document_id": "d1",
            "chunk_id": "c2",
            "text": "best match",
            "score": 0.5,
            "source": "ingest",
        },
        {
            "document_id": "d1",
            "chunk_id": "c3",
            "text": "also d1",
            "score": 0.4,
            "source": "ingest",
        },
        {
            "document_id": "d1",
            "chunk_id": "c4",
            "text": "overflow d1",
            "score": 0.3,
            "source": "ingest",
        },
        {
            "document_id": "d2",
            "chunk_id": "c5",
            "text": "other",
            "score": 0.2,
            "source": "ingest",
        },
    ]
    llm = AsyncMock()
    llm.complete = AsyncMock(return_value="1, 2, 3, 4, 0")
    vs = _VS(hits)
    svc = RetrievalService(
        embeddings=_Emb(),
        vectorstore=vs,
        prefetch=10,
        rerank_mode="llm",
        rerank_candidates=20,
        rerank_top_k=5,
        rerank_max_per_doc=2,
        rerank_min_score=0.0,
        llm=llm,
    )
    meta = await svc.retrieve_with_meta("best", limit=5)
    out = meta.hits
    assert llm.complete.await_count == 1
    assert out[0]["chunk_id"] == "c2"
    assert meta.rerank_mode == "llm"
    assert "rerank_ms" in meta.latency_ms
    assert meta.rerank_scores[0]["chunk_id"] == "c2"
    # max 2 from d1
    d1 = [h for h in out if h["document_id"] == "d1"]
    assert len(d1) <= 2


@pytest.mark.asyncio
async def test_rerank_min_score_filters() -> None:
    hits = [
        {"document_id": "d1", "chunk_id": "c1", "text": "a", "score": 0.9},
        {"document_id": "d2", "chunk_id": "c2", "text": "b", "score": 0.1},
    ]
    svc = RetrievalService(
        embeddings=_Emb(),
        vectorstore=_VS(hits),
        rerank_mode="none",
        rerank_top_k=5,
        rerank_min_score=0.5,
    )
    out = await svc.retrieve("q", limit=5)
    assert [h["chunk_id"] for h in out] == ["c1"]
