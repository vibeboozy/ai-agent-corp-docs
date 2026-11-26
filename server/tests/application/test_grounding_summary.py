"""
ANCHOR: tests.application.test_grounding_summary
PURPOSE: Grounded answers are complete sentences; quotes not mid-chunk stubs.
Dependencies: GroundingService
"""

from __future__ import annotations

from app.application.grounding.service import GroundingService


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
        draft=None,
        query="Кто отвечает за планирование поставок?",
    )
    assert result.ok
    assert result.citations[0]["chunk_id"] == "c72"
    assert "Менеджер по поставке" in (result.answer_text or "")
    assert not (result.citations[0]["quote"] or "").lower().startswith("проекта.")


def test_ground_uses_draft_when_overlapping_chunk() -> None:
    svc = GroundingService()
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
        "За планирование поставок отвечает Менеджер по поставке, "
        "при его отсутствии — Аккаунт-менеджер."
    )
    result = svc.ground(candidates=candidates, draft=draft, query="планирование поставок")
    assert result.ok
    assert "Менеджер по поставке" in (result.answer_text or "")
    assert not (result.answer_text or "").endswith("Аккаунт-менедже")  # complete
