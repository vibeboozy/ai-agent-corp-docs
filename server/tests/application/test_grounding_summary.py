"""
ANCHOR: tests.application.test_grounding_summary
PURPOSE: Grounded answers are short human lines; quotes not mid-chunk stubs.
Dependencies: GroundingService
"""

from __future__ import annotations

from app.application.grounding.service import GroundingService
from app.domain.glossary import AbbreviationGlossary


def test_ground_prefers_lexically_relevant_chunk() -> None:
    svc = GroundingService(min_citations=1, min_score=0.0)
    candidates = [
        {
            "document_id": "d1",
            "chunk_id": "c17",
            "text": "проекта. **17.3.** Исполнители выполняют работы по план-графику.",
            "score": 1.0,
            "document_title": "Регламент",
            "locator": "17.3.",
        },
        {
            "document_id": "d1",
            "chunk_id": "c72",
            "text": (
                "7.2. Планирование поставок. "
                "За планирование поставок отвечает Менеджер по поставке, при его отсутствии – АМ."
            ),
            "score": 0.35,
            "document_title": "Регламент",
            "locator": "7.2.",
        },
    ]
    result = svc.ground(
        candidates=candidates,
        draft="Ответ: Менеджер по поставке (при отсутствии — АМ).",
        query="Кто отвечает за планирование поставок?",
    )
    assert result.ok
    assert result.citations[0]["chunk_id"] == "c72"
    answer = result.answer_text or ""
    assert answer.startswith("Ответ:")
    assert "Источник:" in answer
    assert "Цитата:" in answer
    assert "Менеджер по поставке" in answer
    assert not (result.citations[0]["quote"] or "").lower().startswith("проекта.")


def test_ground_uses_draft_when_overlapping_chunk() -> None:
    svc = GroundingService(glossary=AbbreviationGlossary.from_defaults())
    candidates = [
        {
            "document_id": "d1",
            "chunk_id": "c1",
            "text": "За планирование поставок отвечает Менеджер по поставке.",
            "score": 0.9,
            "document_title": "Регламент",
        }
    ]
    draft = (
        "Ответ: За планирование поставок отвечает Менеджер по поставке."
    )
    result = svc.ground(candidates=candidates, draft=draft, query="планирование поставок")
    assert result.ok
    answer = result.answer_text or ""
    assert answer.startswith("Ответ:")
    assert "Менеджер по поставке" in answer
    assert "Источник:" in answer
    assert not answer.splitlines()[0].endswith("Аккаунт-менедже")  # complete


def test_ground_answer_stops_before_next_numbered_clause() -> None:
    """Chunk bleed ``…Компании. **10.`` must not appear in answer/summary text."""
    svc = GroundingService(min_citations=1, min_score=0.0)
    chunk = (
        "**9.5.** Договоры на закупку подписывают уполномоченные представители "
        "юридических лиц Компании. **10."
    )
    candidates = [
        {
            "document_id": "d1",
            "chunk_id": "c95",
            "text": chunk,
            "score": 0.95,
            "document_title": "Регламент закупок",
            "locator": "9.5.",
        }
    ]
    result = svc.ground(
        candidates=candidates,
        draft="Ответ: Уполномоченные представители юридических лиц Компании.",
        query="Кто подписывает договоры на закупку?",
    )
    assert result.ok
    answer = result.answer_text or ""
    assert answer.startswith("Ответ:")
    assert "Источник:" in answer
    assert "Цитата:" in answer
    assert "юридических лиц Компании" in answer
    assert "**10" not in answer
    assert "**9.5" not in answer.splitlines()[0]
    assert not answer.rstrip().endswith("**10.")
    assert result.citations[0]["locator"] == "9.5"
    quote = result.citations[0]["quote"] or ""
    assert "**10" not in quote


def test_ground_strips_think_from_draft_before_answer() -> None:
    """First-generate path: CoT in draft must not leak into answer_text."""
    svc = GroundingService()
    chunk = "За планирование рисков отвечает руководитель проекта."
    candidates = [
        {
            "document_id": "d1",
            "chunk_id": "c1",
            "text": chunk,
            "score": 0.95,
            "document_title": "Регламент рисков",
        }
    ]
    dirty = (
        "<think>\nThe user asks who plans risks; cite the regulation.\n</think>\n"
        "Ответ: За планирование рисков отвечает руководитель проекта."
    )
    result = svc.ground(
        candidates=candidates, draft=dirty, query="Кто планирует риски?"
    )
    assert result.ok
    answer = result.answer_text or ""
    assert answer.startswith("Ответ:")
    assert "<think>" not in answer.lower()
    assert "</think>" not in answer.lower()
    assert "руководитель проекта" in answer
    assert "Источник:" in answer
