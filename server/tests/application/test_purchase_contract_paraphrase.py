"""
ANCHOR: tests.application.test_purchase_contract_paraphrase
PURPOSE: Regression — purchase-contract WHO question must be a short paraphrase.
Dependencies: GroundingService; answer_format
"""

from __future__ import annotations

from app.application.dialogue.answer_format import (
    enforce_short_paraphrase,
    extract_short_paraphrase,
    format_source_line,
    looks_like_regulation_copy,
    normalize_locator,
)
from app.application.grounding.service import GroundingService

_QUERY = "Кто подписывает договоры на закупку?"
_CHUNK = (
    "**9.5.** Все субподрядные договоры по ИБ проектам, кроме перепродажи "
    "вендорских сервисов, заключаются от юридических лиц Компании. **10."
)
_LOCATOR_FULL = (
    "9.5. Все субподрядные договоры по ИБ проектам, кроме перепродажи "
    "вендорских сервисов, заключаются от юридических лиц Компании"
)


def test_extract_paraphrase_purchase_contract_who() -> None:
    got = extract_short_paraphrase(_QUERY, _CHUNK)
    assert got.lower().startswith("юридические лица компании")
    assert "заключаются" not in got.lower()
    assert "субподряд" not in got.lower()
    assert "…" not in got and "..." not in got
    assert not got.rstrip().endswith("от")


def test_enforce_rejects_mid_clause_truncation() -> None:
    dumped = (
        "Все субподрядные договоры по ИБ проектам, кроме перепродажи "
        "вендорских сервисов, заключаются от…"
    )
    assert looks_like_regulation_copy(dumped, _CHUNK) or dumped.endswith("…")
    got = enforce_short_paraphrase(dumped, query=_QUERY, quote=_CHUNK)
    assert "юридические лица компании" in got.lower()
    assert "заключаются от" not in got.lower()
    assert "…" not in got


def test_source_line_point_number_only() -> None:
    assert normalize_locator(_LOCATOR_FULL) == "9.5"
    line = format_source_line(
        document_title="Пресейловая деятельность Дирекции ИБ",
        locator=_LOCATOR_FULL,
    )
    assert line == "Источник: «Пресейловая деятельность Дирекции ИБ», п. 9.5."
    assert "субподряд" not in line
    assert "заключаются" not in line


def test_ground_purchase_contract_short_paraphrase_without_draft() -> None:
    """No LLM draft: still must not dump / truncate the regulation clause."""
    svc = GroundingService(min_citations=1, min_score=0.0)
    result = svc.ground(
        candidates=[
            {
                "document_id": "presale",
                "chunk_id": "c95",
                "text": _CHUNK,
                "score": 0.96,
                "document_title": "Пресейловая деятельность Дирекции ИБ",
                "locator": _LOCATOR_FULL,
            }
        ],
        draft=None,
        query=_QUERY,
    )
    assert result.ok
    answer = result.answer_text or ""
    first = answer.splitlines()[0]
    assert first.startswith("Ответ:")
    assert "Юридические лица Компании" in first
    assert "заключаются" not in first.lower()
    assert "субподряд" not in first.lower()
    assert "…" not in first
    assert "Согласно регламенту" not in first
    source = [ln for ln in answer.splitlines() if ln.startswith("Источник:")][0]
    assert source == "Источник: «Пресейловая деятельность Дирекции ИБ», п. 9.5."
    assert result.citations[0]["locator"] == "9.5"


def test_ground_purchase_contract_repairs_quote_dump_draft() -> None:
    dump = (
        "Ответ: Все субподрядные договоры по ИБ проектам, кроме перепродажи "
        "вендорских сервисов, заключаются от юридических лиц Компании.\n"
        "Источник: «x», п. 9.5.\n"
        "Цитата: «y»"
    )
    svc = GroundingService(min_citations=1, min_score=0.0)
    result = svc.ground(
        candidates=[
            {
                "document_id": "presale",
                "chunk_id": "c95",
                "text": _CHUNK,
                "score": 0.96,
                "document_title": "Пресейловая деятельность Дирекции ИБ",
                "locator": "9.5.",
            }
        ],
        draft=dump,
        query=_QUERY,
    )
    assert result.ok
    first = (result.answer_text or "").splitlines()[0]
    assert "Юридические лица Компании" in first
    assert "Все субподрядные" not in first
    assert "заключаются от" not in first.lower()
