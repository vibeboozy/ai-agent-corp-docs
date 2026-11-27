"""
ANCHOR: tests.application.test_weak_hit_escalate
PURPOSE: Weak/irrelevant retrieval must escalate — never a false grounded answer.
Dependencies: GroundingService; dialogue graph; Fake ports
Bug: Q «процент пороговой маржинальности… Дирекции ИБ» answered from
unrelated «согласование Директора… бюджета» with scores ~0.47 and tiny chunks.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.application.dialogue.graph import build_dialogue_graph
from app.application.dialogue.nodes import DialogueDeps
from app.application.grounding.service import GroundingService
from app.application.retrieval.service import RetrievalService
from app.application.text_util import lexical_relevance


_MARGIN_Q = (
    "Какой точный процент пороговой маржинальности установлен в Дирекции ИБ?"
)


class _FakeLLM:
    def __init__(self, *, label: str = "specific", draft: str = "UNSUPPORTED") -> None:
        self._label = label
        self._draft = draft
        self.complete = AsyncMock(side_effect=self._complete)

    async def _complete(self, *, system: str, user: str, temperature: float | None = None) -> str:
        _ = (system, user, temperature)
        return self._draft

    async def classify_specificity(
        self, user_message: str, history: list[str] | None = None
    ) -> str:
        _ = (user_message, history)
        return self._label


class _FakeEmbeddings:
    async def embed_dense(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]

    async def embed_sparse(self, texts: list[str]) -> list[dict[str, float]]:
        return [{t: 1.0 for t in (text.lower().split()[:3] or ["x"])} for text in texts]


class _FakeVectorStore:
    def __init__(self, hits: list[dict[str, Any]]) -> None:
        self._hits = hits

    async def search(
        self,
        query: str,
        *,
        limit: int = 5,
        dense_vector: list[float] | None = None,
        sparse_vector: dict[str, float] | None = None,
    ) -> list[dict[str, Any]]:
        _ = (query, limit, dense_vector, sparse_vector)
        return list(self._hits)


_WEAK_IRRELEVANT_HITS = [
    {
        "document_id": "dib-presale",
        "chunk_id": "c-budget-47",
        "text": (
            "Согласование Директора по бюджету подразделения проводится "
            "ежегодно в рамках планирования расходов и утверждения лимитов."
        ),
        "score": 0.47,
        "document_title": "Пресейловая деятельность Дирекции ИБ",
        "locator": "3.1.",
        "source": "ingest",
    },
    {
        "document_id": "dib-presale",
        "chunk_id": "c-budget-41",
        "text": (
            "Директор утверждает бюджетные заявки после согласования "
            "с финансовой службой и руководителями направлений."
        ),
        "score": 0.41,
        "document_title": "Пресейловая деятельность Дирекции ИБ",
        "locator": "3.2.",
        "source": "ingest",
    },
    {
        "document_id": "dib-presale",
        "chunk_id": "c-tiny-34",
        "text": "согласование Директора бюджета",
        "score": 0.34,
        "document_title": "Пресейловая деятельность Дирекции ИБ",
        "locator": "3.3.",
        "source": "ingest",
    },
]


def test_lexical_relevance_matches_russian_morphology() -> None:
    passage = (
        "Пороговая маржинальность в Дирекции ИБ составляет пятнадцать процентов "
        "от суммы проекта и применяется при оценке коммерческих предложений."
    )
    assert lexical_relevance(_MARGIN_Q, passage) >= 0.12
    bad = (
        "Согласование Директора по бюджету подразделения проводится "
        "ежегодно в рамках планирования расходов и утверждения лимитов."
    )
    assert lexical_relevance(_MARGIN_Q, bad) < 0.12


def test_ground_escalates_weak_irrelevant_margin_hits() -> None:
    """Scores ~0.47 with no topical link must not produce status=answered."""
    svc = GroundingService(
        min_citations=1, min_score=0.25, min_query_overlap=0.12
    )
    result = svc.ground(
        candidates=list(_WEAK_IRRELEVANT_HITS),
        draft=None,  # LLM UNSUPPORTED path
        query=_MARGIN_Q,
    )
    assert result.ok is False
    assert result.reason == "irrelevant_citations"
    assert result.answer_text is None


def test_ground_escalates_when_draft_paraphrases_unrelated_quote() -> None:
    """Even a fluent draft must not stick if the quote is off-topic."""
    svc = GroundingService(
        min_citations=1, min_score=0.0, min_query_overlap=0.12
    )
    draft = "Ответ: Согласование Директора по бюджету."
    result = svc.ground(
        candidates=list(_WEAK_IRRELEVANT_HITS),
        draft=draft,
        query=_MARGIN_Q,
    )
    assert result.ok is False
    assert result.reason == "irrelevant_citations"


def test_ground_still_answers_when_hit_is_topically_relevant() -> None:
    """New relevance gates must not block a real matching clause."""
    svc = GroundingService(
        min_citations=1, min_score=0.25, min_query_overlap=0.12
    )
    hits = [
        {
            "document_id": "d1",
            "chunk_id": "c72",
            "text": (
                "7.2. Планирование поставок. "
                "За планирование поставок отвечает Менеджер по поставке, "
                "при его отсутствии – АМ."
            ),
            "score": 0.72,
            "document_title": "Регламент",
            "locator": "7.2.",
        }
    ]
    result = svc.ground(
        candidates=hits,
        draft="Ответ: Менеджер по поставке (при отсутствии — АМ).",
        query="Кто отвечает за планирование поставок?",
    )
    assert result.ok is True, result
    assert "Менеджер по поставке" in (result.answer_text or "")


def test_ground_rejects_tiny_few_word_chunks() -> None:
    svc = GroundingService(min_citations=1, min_score=0.0, min_query_overlap=0.0)
    result = svc.ground(
        candidates=[
            {
                "document_id": "d1",
                "chunk_id": "tiny",
                "text": "согласование Директора бюджета",
                "score": 0.9,
                "document_title": "Регламент",
            }
        ],
        draft=None,
        query=_MARGIN_Q,
    )
    assert result.ok is False
    assert result.reason in {"insufficient_citations", "irrelevant_citations"}


@pytest.mark.asyncio
async def test_graph_weak_irrelevant_hits_escalate() -> None:
    deps = DialogueDeps(
        llm=_FakeLLM(label="specific", draft="UNSUPPORTED"),
        retrieval=RetrievalService(
            embeddings=_FakeEmbeddings(),
            vectorstore=_FakeVectorStore(list(_WEAK_IRRELEVANT_HITS)),
            lexical_weight=0.35,
        ),
        grounding=GroundingService(
            min_citations=1, min_score=0.25, min_query_overlap=0.12
        ),
        quality_email="quality@example.invalid",
    )
    graph = build_dialogue_graph(deps)
    out = await graph.ainvoke(
        {
            "user_message": _MARGIN_Q,
            "history": [],
            "clarify_turns": 0,
            "max_clarify_turns": 3,
        }
    )
    assert out["outcome"] == "escalate"
    # Blended score floor and/or query-overlap gate both escalate (never answer).
    assert out["escalation_reason"] in {
        "irrelevant_citations",
        "insufficient_citations",
    }
    assert out.get("grounded") is False
    assert not out.get("draft_answer")
