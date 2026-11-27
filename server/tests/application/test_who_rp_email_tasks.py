"""
ANCHOR: tests.application.test_who_rp_email_tasks
PURPOSE: WHO extract keeps РП; glossary must not expand preposition «по» as ПО.
Dependencies: answer_format; GroundingService; glossary
"""

from __future__ import annotations

from app.application.dialogue.answer_format import (
    enforce_short_paraphrase,
    extract_short_paraphrase,
)
from app.application.grounding.service import GroundingService
from app.domain.glossary import AbbreviationGlossary

_QUERY = "Кто назначает задачи сотрудникам субподрядчика по электронной почте?"
_CHUNK = "РП назначает задачи сотрудникам субподрядчика по электронной почте."


def test_extract_keeps_rp_subject_not_task_object() -> None:
    got = extract_short_paraphrase(_QUERY, _CHUNK)
    assert got in {"РП", "РП.", "Руководитель проекта", "Руководитель проекта."}
    assert "задачи" not in got.lower()
    assert "субподряд" not in got.lower()
    assert not got.lower().startswith("задачи")


def test_enforce_repairs_object_dump_to_rp() -> None:
    dumped = "Задачи сотрудникам субподрядчика по электронной почте…"
    got = enforce_short_paraphrase(dumped, query=_QUERY, quote=_CHUNK)
    assert got in {"РП", "РП.", "Руководитель проекта", "Руководитель проекта."}
    assert "задачи" not in got.lower()
    assert "…" not in got


def test_glossary_does_not_expand_preposition_po() -> None:
    g = AbbreviationGlossary.from_defaults()
    assert "Программное обеспечение" not in g.expand_for_display(
        "задачи по электронной почте"
    )
    assert "ПО (Программное обеспечение)" in g.expand_for_display(
        "внедрение ПО на проекте"
    )
    assert "Программное обеспечение" not in g.expand(
        "назначает задачи по электронной почте"
    )


def test_ground_who_email_tasks_expands_rp_only() -> None:
    svc = GroundingService(
        min_citations=1,
        min_score=0.0,
        glossary=AbbreviationGlossary.from_defaults(),
    )
    result = svc.ground(
        candidates=[
            {
                "document_id": "d1",
                "chunk_id": "c-email",
                "text": _CHUNK,
                "score": 0.97,
                "document_title": "Проектная деятельность Дирекции ИБ",
                "locator": "4.2.",
            }
        ],
        draft=None,
        query=_QUERY,
    )
    assert result.ok
    first = (result.answer_text or "").splitlines()[0]
    assert first.startswith("Ответ:")
    assert "РП (Руководитель проекта)" in first or first == "Ответ: Руководитель проекта."
    assert "задачи" not in first.lower()
    assert "Программное обеспечение" not in first
    assert "ПО (" not in first
