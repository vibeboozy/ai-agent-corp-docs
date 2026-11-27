"""
ANCHOR: tests.application.test_citation_dedupe
PURPOSE: Learned re-ask must not surface the same source/quote 3× in citations.
Dependencies: grounding.dedupe_citations, GroundingService, RetrievalService
"""

from __future__ import annotations

from app.application.grounding.service import GroundingService, dedupe_citations
from app.application.retrieval.service import RetrievalService


def test_dedupe_citations_by_chunk_id() -> None:
    cites = [
        {
            "document_id": "d1",
            "chunk_id": "c1",
            "quote": "А",
            "locator": "1.1",
        },
        {
            "document_id": "d1",
            "chunk_id": "c1",
            "quote": "А (повтор)",
            "locator": "1.1",
        },
    ]
    out = dedupe_citations(cites)
    assert len(out) == 1
    assert out[0]["chunk_id"] == "c1"


def test_dedupe_citations_identical_quote_across_learned_docs() -> None:
    """Triple officer ingest → three learned-* docs, same quote — UI needs 1."""
    quote = "Цвет логотипа — Pantone 286 C по брендбуку."
    cites = [
        {
            "document_id": f"learned-aaa{i}",
            "chunk_id": f"c-{i}",
            "quote": quote,
            "document_title": "Канонический ответ офицера качества",
            "locator": "",
            "score": 0.9 - i * 0.01,
        }
        for i in range(3)
    ]
    out = dedupe_citations(cites, max_n=3)
    assert len(out) == 1
    assert out[0]["quote"] == quote


def test_ground_learned_keeps_single_citation() -> None:
    svc = GroundingService(min_citations=1, min_score=0.0, min_query_overlap=0.0)
    text = (
        "За планирование поставок отвечает Менеджер по поставке, "
        "при его отсутствии — Аккаунт-менеджер."
    )
    candidates = [
        {
            "document_id": f"learned-x{i}",
            "chunk_id": f"chunk-{i}",
            "text": text,
            "score": 0.95 - i * 0.01,
            "document_title": "Канонический ответ офицера качества",
            "source": "learned",
        }
        for i in range(3)
    ]
    result = svc.ground(
        candidates=candidates,
        draft="Ответ: Менеджер по поставке (при отсутствии — Аккаунт-менеджер).",
        query="Кто отвечает за планирование поставок?",
    )
    assert result.ok
    assert len(result.citations) == 1
    assert result.citations[0]["chunk_id"].startswith("chunk-")
    assert "source" not in result.citations[0]
    # Triple identical learned bodies must not inflate the citations block.
    assert len({c["quote"] for c in result.citations}) == 1


def test_retrieval_dedupe_identical_text() -> None:
    hits = [
        {
            "document_id": "learned-a",
            "chunk_id": "c-a",
            "text": "Один и тот же канонический ответ.",
            "score": 0.9,
            "source": "learned",
        },
        {
            "document_id": "learned-b",
            "chunk_id": "c-b",
            "text": "Один и тот же канонический ответ.",
            "score": 0.88,
            "source": "learned",
        },
        {
            "document_id": "reg-1",
            "chunk_id": "c-other",
            "text": "Другой фрагмент регламента про закупки.",
            "score": 0.5,
            "source": "ingest",
        },
    ]
    out = RetrievalService._dedupe_identical_text(hits)
    assert len(out) == 2
    assert out[0]["chunk_id"] == "c-a"
    assert out[1]["chunk_id"] == "c-other"
