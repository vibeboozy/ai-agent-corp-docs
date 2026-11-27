"""
ANCHOR: tests.application.test_near_duplicate_when
PURPOSE: Near-identical WHEN questions must not diverge into paraphrase_required
         vs answered; off-topic neighbors escalate; margin weak-hits still escalate.
Dependencies: GroundingService; RetrievalService blend; answer_format
Bug: Q1 (координатор… Расчётом) answered п. 2.7; Q2 (Дирекции ИБ… полной
информации) escalated paraphrase_required despite same clause.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.application.dialogue.answer_format import (
    enforce_short_paraphrase,
    extract_short_paraphrase,
    strip_regulation_noise,
)
from app.application.grounding.service import GroundingService
from app.application.retrieval.service import RetrievalService
from app.application.text_util import lexical_overlap, lexical_relevance
from app.domain.glossary import AbbreviationGlossary


_CLAUSE_27 = (
    "Если предоставлена полная информация, Координатор департамента назначает РП "
    "в соответствии с итоговым Расчётом проекта в течение 1 рабочего дня."
)
_NEIGHBOR = (
    "Дирекция ИБ обеспечивает предоставление полной информации по проектам "
    "в рамках пресейловой деятельности подразделения."
)
_Q1 = (
    "В какой срок координатор департамента назначает РП "
    "в соответствии с итоговым Расчётом проекта?"
)
_Q2 = (
    "В какой срок назначается РП в Дирекции ИБ "
    "при предоставлении полной информации?"
)
_MARGIN_Q = (
    "Какой точный процент пороговой маржинальности установлен в Дирекции ИБ?"
)


def test_q2_morphology_relevance_vs_exact_overlap() -> None:
    """Exact Jaccard under-counts RU forms; prefix relevance must still clear the floor."""
    assert lexical_overlap(_Q2, _CLAUSE_27) == 0.0
    assert lexical_relevance(_Q2, _CLAUSE_27) >= 0.12


def test_strip_keeps_bare_day_count() -> None:
    assert strip_regulation_noise("1 рабочего дня.") == "1 рабочего дня."
    assert "2.7" not in strip_regulation_noise("2.7. Координатор назначает РП.")


def test_when_extract_keeps_v_techenie_and_day_count() -> None:
    got = extract_short_paraphrase(_Q2, _CLAUSE_27)
    assert got.lower().startswith("в течение")
    assert "1" in got
    assert "рабочего дня" in got.lower()
    enforced = enforce_short_paraphrase(
        _CLAUSE_27, query=_Q2, quote=_CLAUSE_27
    )
    assert "1" in enforced
    assert enforced.lower().startswith("в течение")


def test_ground_q1_and_q2_both_answer_from_clause_27() -> None:
    svc = GroundingService(
        min_citations=1,
        min_score=0.25,
        min_query_overlap=0.12,
        glossary=AbbreviationGlossary.from_defaults(),
    )
    hits = [
        {
            "document_id": "dib-project",
            "chunk_id": "c27",
            "text": _CLAUSE_27,
            "score": 0.55,
            "document_title": "Проектная деятельность Дирекции ИБ.docx",
            "locator": "2.7.",
        },
        {
            "document_id": "dib-presale",
            "chunk_id": "c-neighbor",
            "text": _NEIGHBOR,
            "score": 0.70,
            "document_title": "Пресейловая деятельность Дирекции ИБ",
            "locator": "1.1.",
        },
    ]
    for q in (_Q1, _Q2):
        result = svc.ground(
            candidates=list(hits),
            draft="Ответ: В течение одного рабочего дня.",
            query=q,
        )
        assert result.ok is True, (q, result.reason)
        assert result.answer_text
        assert "рабочего дня" in result.answer_text.lower()
        assert "2.7" in result.answer_text
        assert result.citations
        assert "в течение 1 рабочего дня" in (
            result.citations[0].get("quote") or ""
        ).lower()


def test_ground_when_neighbor_only_escalates_not_paraphrase_required() -> None:
    """Neighbor shares «Дирекции / полной информации» but has no deadline → escalate."""
    svc = GroundingService(
        min_citations=1, min_score=0.25, min_query_overlap=0.12
    )
    result = svc.ground(
        candidates=[
            {
                "document_id": "d",
                "chunk_id": "n",
                "text": _NEIGHBOR,
                "score": 0.70,
                "document_title": "Пресейловая",
                "locator": "1.1.",
            }
        ],
        draft=None,
        query=_Q2,
    )
    assert result.ok is False
    assert result.reason == "irrelevant_citations"
    assert result.answer_text is None


def test_blend_boosts_clause_27_for_q2_morphology() -> None:
    """Retrieval blend must not leave clause 2.7 at lex=0 for Q2 word forms."""
    svc = RetrievalService(
        embeddings=None,  # type: ignore[arg-type]
        vectorstore=None,  # type: ignore[arg-type]
        lexical_weight=0.35,
    )
    blended = svc._blend_lexical(
        _Q2,
        [
            {
                "document_id": "d",
                "chunk_id": "neighbor",
                "text": _NEIGHBOR,
                "score": 0.70,
                "locator": "1.1.",
            },
            {
                "document_id": "d",
                "chunk_id": "c27",
                "text": _CLAUSE_27,
                "score": 0.60,
                "locator": "2.7.",
            },
        ],
    )
    by_id = {h["chunk_id"]: h for h in blended}
    assert float(by_id["c27"]["lexical_score"]) >= 0.12
    # Morphology-aware blend keeps 2.7 competitive (not stuck at floor demotion).
    assert float(by_id["c27"]["score"]) > 0.2


def test_margin_still_escalates_on_budget_hits() -> None:
    svc = GroundingService(
        min_citations=1, min_score=0.25, min_query_overlap=0.12
    )
    result = svc.ground(
        candidates=[
            {
                "document_id": "dib",
                "chunk_id": "budget",
                "text": (
                    "Согласование Директора по бюджету подразделения проводится "
                    "ежегодно в рамках планирования расходов и утверждения лимитов."
                ),
                "score": 0.47,
                "document_title": "Пресейловая деятельность Дирекции ИБ",
                "locator": "3.1.",
            }
        ],
        draft=None,
        query=_MARGIN_Q,
    )
    assert result.ok is False
    assert result.reason == "irrelevant_citations"
