"""
ANCHOR: tests.application.test_answer_format
PURPOSE: Human-readable Ответ/Источник/Цитата shape + RCTIOSE-adapted prompt.
Dependencies: dialogue.answer_format; GroundingService
"""

from __future__ import annotations

from app.application.dialogue.answer_format import (
    build_answer_system_prompt,
    build_answer_user_prompt,
    extract_answer_body,
    format_human_answer,
    summary_from_answer,
)
from app.application.grounding.service import GroundingService


def test_system_prompt_includes_structure_and_no_tool_calls() -> None:
    prompt = build_answer_system_prompt("- корпоративные регламенты и процессы: тест")
    assert "Ответ:" in prompt
    assert "Источник:" in prompt
    assert "Цитата:" in prompt
    assert "UNSUPPORTED" in prompt
    assert "УЖЕ выполнен" in prompt or "уже выполнен" in prompt.lower()
    assert "<think>" in prompt  # instructs not to emit it
    assert "корпоративные регламенты" in prompt
    assert "2-3 дня" in prompt  # negative few-shot


def test_user_prompt_lists_passages() -> None:
    user = build_answer_user_prompt(
        question="В какой срок назначается РП?",
        passages=["[0] (2.7.) Если предоставлена полная информация…"],
    )
    assert "В какой срок назначается РП?" in user
    assert "[0] (2.7.)" in user
    assert "Ответ / Источник / Цитата" in user


def test_extract_answer_body_from_structured() -> None:
    raw = (
        "Ответ: В течение одного рабочего дня при наличии полной информации.\n"
        "Источник: «Проектная деятельность Дирекции ИБ.docx», п. 2.7.\n"
        "Цитата: «Если предоставлена полная информация, Координатор департамента "
        "назначает РП.»"
    )
    assert extract_answer_body(raw) == (
        "В течение одного рабочего дня при наличии полной информации."
    )


def test_format_human_answer_three_lines() -> None:
    text = format_human_answer(
        answer="В течение одного рабочего дня при наличии полной информации.",
        document_title="Проектная деятельность Дирекции ИБ.docx",
        locator="2.7.",
        quote=(
            "Если предоставлена полная информация, Координатор департамента "
            "назначает РП в соответствии с итоговым Расчётом проекта "
            "в течение 1 рабочего дня."
        ),
    )
    lines = text.splitlines()
    assert lines[0].startswith("Ответ:")
    assert "одного рабочего дня" in lines[0]
    assert lines[1].startswith("Источник:")
    assert "Проектная деятельность Дирекции ИБ.docx" in lines[1]
    assert "п. 2.7" in lines[1]
    assert lines[2].startswith("Цитата:")
    assert "Координатор департамента" in lines[2]


def test_summary_prefers_answer_line() -> None:
    full = (
        "Ответ: В течение одного рабочего дня при наличии полной информации.\n"
        "Источник: «Проектная деятельность Дирекции ИБ.docx», п. 2.7.\n"
        "Цитата: «Если предоставлена полная информация…»"
    )
    summary = summary_from_answer(full, 480)
    assert summary.startswith("Ответ:")
    assert "одного рабочего дня" in summary
    assert "Источник:" not in summary
    assert "Цитата:" not in summary


def test_ground_emits_human_template_without_draft() -> None:
    svc = GroundingService(min_citations=1, min_score=0.0)
    chunk = (
        "Если предоставлена полная информация, Координатор департамента назначает РП "
        "в соответствии с итоговым Расчётом проекта в течение 1 рабочего дня."
    )
    result = svc.ground(
        candidates=[
            {
                "document_id": "d1",
                "chunk_id": "c27",
                "text": chunk,
                "score": 0.97,
                "document_title": "Проектная деятельность Дирекции ИБ.docx",
                "locator": "2.7.",
            }
        ],
        draft=None,
        query="В какой срок назначается РП в Дирекции ИБ при предоставлении полной информации?",
    )
    assert result.ok
    answer = result.answer_text or ""
    assert answer.startswith("Ответ:")
    assert "Источник:" in answer
    assert "Цитата:" in answer
    assert "п. 2.7" in answer
    assert "Согласно регламенту" not in answer


def test_ground_uses_structured_draft_answer_line() -> None:
    svc = GroundingService()
    chunk = (
        "Если предоставлена полная информация, Координатор департамента назначает РП "
        "в течение 1 рабочего дня."
    )
    draft = (
        "Ответ: В течение одного рабочего дня при наличии полной информации.\n"
        "Источник: «wrong.docx», п. 99.\n"
        "Цитата: «hallucinated»"
    )
    result = svc.ground(
        candidates=[
            {
                "document_id": "d1",
                "chunk_id": "c1",
                "text": chunk,
                "score": 0.9,
                "document_title": "Проектная деятельность Дирекции ИБ.docx",
                "locator": "2.7.",
            }
        ],
        draft=draft,
        query="срок назначения РП полная информация",
    )
    assert result.ok
    answer = result.answer_text or ""
    # Human short answer kept; Источник/Цитата overridden from grounded citation.
    assert "В течение одного рабочего дня при наличии полной информации." in answer
    assert "Проектная деятельность Дирекции ИБ.docx" in answer
    assert "п. 2.7" in answer
    assert "wrong.docx" not in answer
    assert "hallucinated" not in answer
    assert "1 рабочего дня" in answer  # quote from chunk
