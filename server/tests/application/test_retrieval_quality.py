"""
ANCHOR: tests.application.test_retrieval_quality
PURPOSE: Lexical blend demotes irrelevant high vector scores; glossary expands query.
Dependencies: RetrievalService + Fake ports
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

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


@pytest.mark.asyncio
async def test_purchase_who_surfaces_95_over_ds_timing_neighbors() -> None:
    """GS-02: п.9.5 must enter top-k despite weaker vector vs DS/timing rivals."""
    hits = [
        {
            "document_id": "dbrct",
            "chunk_id": "c-8.7",
            "text": (
                "8.7. За 5 рабочих дней до наступления плановой даты подписания "
                "Договора РП запрашивает у АМ подтверждение, что договор будет подписан."
            ),
            "score": 0.72,
            "locator": "8.7.",
            "document_title": "Проектная деятельность ДБРЦТ",
            "source": "ingest",
        },
        {
            "document_id": "dbrct",
            "chunk_id": "c-17.6",
            "text": (
                "17.6. В результате изменений может быть подписано ДС с Заказчиком. "
                "РП инициирует подписание ДС аналогично заключению договора."
            ),
            "score": 0.70,
            "locator": "17.6.",
            "document_title": "Проектная деятельность ДБРЦТ",
            "source": "ingest",
        },
        {
            "document_id": "tech",
            "chunk_id": "c-timing",
            "text": "Определены сроки подписания договора и старта исполнения обязательств.",
            "score": 0.68,
            "locator": "15.3.",
            "document_title": "Организация проектной деятельности",
            "source": "ingest",
        },
        {
            "document_id": "tech",
            "chunk_id": "c-20.7",
            "text": (
                "20.7. АМ/Менеджер по продаже решений подписывает ДС с заказчиком."
            ),
            "score": 0.65,
            "locator": "20.7.",
            "document_title": "Организация проектной деятельности",
            "source": "ingest",
        },
        {
            "document_id": "presale",
            "chunk_id": "c-9.5",
            "text": (
                "9.5. Все субподрядные договоры по ИБ проектам, кроме перепродажи "
                "вендорских сервисов, заключаются от юридических лиц Компании."
            ),
            "score": 0.33,
            "locator": "9.5.",
            "document_title": "Пресейловая деятельность Дирекции ИБ",
            "source": "ingest",
        },
    ]
    llm = AsyncMock()
    llm.complete = AsyncMock(return_value="0,1,2,3,4")  # would prefer noise first
    emb = _Emb()
    vs = _VS(hits)
    svc = RetrievalService(
        embeddings=emb,
        vectorstore=vs,
        llm=llm,
        rerank_mode="llm",
        rerank_top_k=5,
        rerank_candidates=20,
        lexical_weight=0.35,
    )
    result = await svc.retrieve_with_meta(
        "Кто подписывает договоры на закупку?", limit=5
    )
    # Synonym expand for hybrid search + skip flaky LLM rerank.
    assert emb.last_texts and "юридических лиц" in emb.last_texts[0]
    assert "субподрядные" in emb.last_texts[0]
    assert result.rerank_mode == "none+purchase_who"
    llm.complete.assert_not_awaited()
    ids = [h["chunk_id"] for h in result.hits]
    assert "c-9.5" in ids
    assert ids[0] == "c-9.5"
