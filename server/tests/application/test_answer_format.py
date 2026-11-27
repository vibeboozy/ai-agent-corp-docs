"""
ANCHOR: tests.application.test_answer_format
PURPOSE: Human-readable Ответ/Источник/Цитата — short, no clause dump, abbr expand.
Dependencies: dialogue.answer_format; GroundingService; glossary
"""

from __future__ import annotations

from app.application.dialogue.answer_format import (
    build_answer_system_prompt,
    build_answer_user_prompt,
    extract_answer_body,
    format_human_answer,
    is_near_quote_duplicate,
    normalize_short_answer,
    strip_regulation_noise,
    summary_from_answer,
)
from app.application.grounding.service import GroundingService
from app.domain.glossary import AbbreviationGlossary


def test_system_prompt_forbids_clause_dump_and_quote_copy() -> None:
    prompt = build_answer_system_prompt("- корпоративные регламенты и процессы: тест")
    assert "Ответ:" in prompt
    assert "номеров пунктов" in prompt or "9.5" in prompt
    assert "не копируй" in prompt.lower() or "НЕ копия" in prompt
    assert "РП (Руководитель проекта)" in prompt
    assert "УЖЕ выполнен" in prompt
    assert "UNSUPPORTED" in prompt


def test_user_prompt_lists_passages() -> None:
    user = build_answer_user_prompt(
        question="В какой срок назначается РП?",
        passages=["[0] (2.7.) Если предоставлена полная информация…"],
    )
    assert "В какой срок назначается РП?" in user
    assert "[0] (2.7.)" in user
    assert "без номеров пунктов" in user


def test_strip_regulation_noise_removes_clause_numbers() -> None:
    raw = (
        "Согласно регламенту «Пресейловая деятельность Дирекции ИБ»: "
        "**9.5.** Договоры на закупку подписывают уполномоченные представители "
        "юридических лиц Компании, п. 9.5."
    )
    cleaned = strip_regulation_noise(raw)
    assert "**9.5" not in cleaned
    assert "п. 9.5" not in cleaned.lower()
    assert "Согласно регламенту" not in cleaned
    assert "юридических лиц Компании" in cleaned


def test_normalize_rejects_full_quote_as_answer() -> None:
    quote = (
        "Если предоставлена полная информация, Координатор департамента назначает РП "
        "в соответствии с итоговым Расчётом проекта в течение 1 рабочего дня."
    )
    assert is_near_quote_duplicate(quote, quote)
    short = normalize_short_answer(quote, quote=quote)
    assert short != quote
    assert len(short) < len(quote)


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


def test_format_human_answer_three_lines_and_expands_abbr() -> None:
    glossary = AbbreviationGlossary.from_defaults()
    text = format_human_answer(
        answer="В течение одного рабочего дня при наличии полной информации (назначается РП).",
        document_title="Проектная деятельность Дирекции ИБ.docx",
        locator="2.7.",
        quote=(
            "Если предоставлена полная информация, Координатор департамента "
            "назначает РП в соответствии с итоговым Расчётом проекта "
            "в течение 1 рабочего дня."
        ),
        glossary=glossary,
    )
    lines = text.splitlines()
    assert lines[0].startswith("Ответ:")
    assert "РП (Руководитель проекта)" in lines[0]
    assert "**" not in lines[0]
    assert "п. 2.7" not in lines[0]
    assert lines[1].startswith("Источник:")
    assert "п. 2.7" in lines[1]
    assert lines[2].startswith("Цитата:")


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


def test_ground_short_answer_not_clause_dump() -> None:
    svc = GroundingService(
        min_citations=1,
        min_score=0.0,
        glossary=AbbreviationGlossary.from_defaults(),
    )
    chunk = (
        "**9.5.** Договоры на закупку подписывают уполномоченные представители "
        "юридических лиц Компании. **10."
    )
    result = svc.ground(
        candidates=[
            {
                "document_id": "d1",
                "chunk_id": "c95",
                "text": chunk,
                "score": 0.95,
                "document_title": "Пресейловая деятельность Дирекции ИБ",
                "locator": "9.5.",
            }
        ],
        draft=(
            "Ответ: Уполномоченные представители юридических лиц Компании.\n"
            "Источник: «x», п. 1.\n"
            "Цитата: «y»"
        ),
        query="Кто подписывает договоры на закупку?",
    )
    assert result.ok
    answer = result.answer_text or ""
    assert answer.startswith("Ответ:")
    first = answer.splitlines()[0]
    assert "**9.5" not in first
    assert "Согласно регламенту" not in first
    assert "юридических лиц Компании" in first
    assert "Источник:" in answer and "п. 9.5" in answer
    assert "Цитата:" in answer
    # Ответ must not equal the full quote body.
    quote_line = [ln for ln in answer.splitlines() if ln.startswith("Цитата:")][0]
    assert first.removeprefix("Ответ:").strip() not in (
        quote_line.removeprefix("Цитата:").strip().strip("«»")
    )


def test_ground_expands_rp_in_answer() -> None:
    svc = GroundingService(
        min_citations=1,
        min_score=0.0,
        glossary=AbbreviationGlossary.from_defaults(),
    )
    chunk = (
        "Если предоставлена полная информация, Координатор департамента назначает РП "
        "в течение 1 рабочего дня."
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
        draft="Ответ: В течение одного рабочего дня назначается РП.\nИсточник: «x», п. 2.7.",
        query="В какой срок назначается РП при полной информации?",
    )
    assert result.ok
    first = (result.answer_text or "").splitlines()[0]
    assert "РП (Руководитель проекта)" in first


def test_ground_without_draft_still_strips_clause_marker() -> None:
    svc = GroundingService(min_citations=1, min_score=0.0)
    chunk = (
        "**9.5.** Договоры на закупку подписывают уполномоченные представители "
        "юридических лиц Компании."
    )
    result = svc.ground(
        candidates=[
            {
                "document_id": "d1",
                "chunk_id": "c95",
                "text": chunk,
                "score": 0.9,
                "document_title": "Регламент",
                "locator": "9.5.",
            }
        ],
        draft=None,
        query="Кто подписывает договоры на закупку?",
    )
    assert result.ok
    first = (result.answer_text or "").splitlines()[0]
    assert first.startswith("Ответ:")
    assert "**9.5" not in first
    assert "Согласно регламенту" not in first
