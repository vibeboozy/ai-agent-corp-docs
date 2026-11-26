"""
ANCHOR: tests.application.test_retrieval_quality
PURPOSE: Lexical blend demotes irrelevant high vector scores; glossary expands query.
Dependencies: RetrievalService + Fake ports
"""

from __future__ import annotations

from typing import Any

import pytest

from app.application.retrieval.service import RetrievalService
from app.domain.glossary import AbbreviationGlossary


class _Emb:
    async def embed_dense(self, texts: list[str]) -> list[list[float]]:
        self.last_texts = list(texts)
        return [[0.1] for _ in texts]

    async def embed_sparse(self, texts: list[str]) -> list[dict[str, float]]:
        return [{"q": 1.0} for _ in texts]


class _VS:
    def __init__(self, hits: list[dict[str, Any]]) -> None:
        self.hits = hits
        self.last_query: str | None = None

    async def search(
        self,
        query: str,
        *,
        limit: int = 5,
        dense_vector: list[float] | None = None,
        sparse_vector: dict[str, float] | None = None,
    ) -> list[dict[str, Any]]:
        _ = (dense_vector, sparse_vector, limit)
        self.last_query = query
        return list(self.hits)


@pytest.mark.asyncio
async def test_lexical_blend_prefers_section_7_2_over_inflated_17() -> None:
    hits = [
        {
            "document_id": "doc1",
            "chunk_id": "bad-17",
            "text": (
                "проекта. Исключением является прямое письменное указание руководителя. "
                "**17.3.** Исполнители команды проекта выполняют работы в соответствии "
                "с утвержденным календарным план-графиком."
            ),
            "score": 1.0,
            "locator": "17.3.",
            "source": "ingest",
        },
        {
            "document_id": "doc1",
            "chunk_id": "good-7-2",
            "text": (
                "7.2. Планирование поставок. "
                "7.2.1. За планирование поставок отвечает Менеджер по поставке, "
                "при его отсутствии – АМ."
            ),
            "score": 0.4,
            "locator": "7.2. Планирование поставок",
            "source": "ingest",
        },
    ]
    emb = _Emb()
    vs = _VS(hits)
    svc = RetrievalService(
        embeddings=emb,
        vectorstore=vs,
        rerank_mode="none",
        rerank_top_k=2,
        lexical_weight=0.55,
    )
    out = await svc.retrieve("Кто отвечает на проекте за планирование поставок?", limit=2)
    assert out[0]["chunk_id"] == "good-7-2"
    assert float(out[0]["score"]) > float(out[1]["score"])


@pytest.mark.asyncio
async def test_glossary_expands_query_before_embed() -> None:
    emb = _Emb()
    vs = _VS([])
    svc = RetrievalService(
        embeddings=emb,
        vectorstore=vs,
        glossary=AbbreviationGlossary.from_defaults(),
    )
    await svc.retrieve_with_meta("Роль РП в проекте", limit=3)
    assert emb.last_texts
    assert "Руководитель проекта" in emb.last_texts[0]
