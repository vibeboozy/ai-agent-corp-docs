"""
ANCHOR: tests.application.test_answer_format
PURPOSE: Human-readable Ответ/Источник/Цитата — short paraphrase, abbr expand.
Dependencies: dialogue.answer_format; GroundingService; glossary
"""

from __future__ import annotations

from app.application.dialogue.answer_format import (
    answer_prompt_mode,
    build_answer_system_prompt,
    build_answer_user_prompt,
    enforce_short_paraphrase,
    extract_answer_body,
    format_human_answer,
    looks_like_regulation_copy,
    strip_regulation_noise,
    summary_from_answer,
)
from app.application.grounding.service import GroundingService
from app.domain.allowed_topics import topics_for_mode
from app.domain.glossary import AbbreviationGlossary


def test_system_prompt_forbids_clause_dump_and_quote_copy() -> None:
    prompt = build_answer_system_prompt(
        "- корпоративные регламенты и процессы: тест",
        domain_mode="regs_only",
    )
    assert "Ответ:" in prompt
    assert "Юридические лица Компании" in prompt
    assert "заключаются от" in prompt  # negative example
    assert "РП (Руководитель проекта)" in prompt
    assert "passages" in prompt.lower()
    assert "UNSUPPORTED" in prompt
    # regs_only → no legal addendum
    assert "Трудовой кодекс" not in prompt
    assert "Конституция" not in prompt
    assert "ст. 91" not in prompt


def test_regs_only_prompt_mode_strips_legal() -> None:
    assert answer_prompt_mode("regs_only") == "regs_only"
    prompt = build_answer_system_prompt(
        topics=topics_for_mode("regs_only"),
        domain_mode="regs_only",
    )
    assert "корпоративн" in prompt.lower()
    assert "learned" in prompt.lower() or "экспертн" in prompt.lower()
    assert "clarify" in prompt.lower() or "escalate" in prompt.lower()
    assert "Трудовой кодекс" not in prompt
    assert "Конституция" not in prompt
    assert "ст. 91" not in prompt
    assert "search_legal" not in prompt


def test_regs_legal_prompt_mode_adds_addendum() -> None:
    assert answer_prompt_mode("regs_legal") == "regs_legal"
    prompt = build_answer_system_prompt(
        topics=topics_for_mode("regs_legal"),
        domain_mode="regs_legal",
    )
    assert "regs_legal" in prompt or "законодательств" in prompt.lower()
    assert "Трудовой кодекс" in prompt
    assert "Конституция" in prompt
    assert "ст. 91" in prompt
    assert "40 часов" in prompt
    assert "не смешивай" in prompt.lower() or "Не смешивай" in prompt
    # Shared base still present
    assert "Юридические лица Компании" in prompt
    assert "UNSUPPORTED" in prompt
    # No fake tool-calling UX
    assert "search_legal(" not in prompt
    assert "search_corporate_docs(" not in prompt
    # Topics bake Конституция + ТК
    assert "Конституция РФ" in prompt
    assert "Трудовой кодекс РФ" in prompt


def test_user_prompt_lists_passages() -> None:
    user = build_answer_user_prompt(
        question="В какой срок назначается РП?",
        passages=["[0] (2.7.) Если предоставлена полная информация…"],
    )
    assert "В какой срок назначается РП?" in user
    assert "[0] (2.7.)" in user
    assert "парафраз" in user.lower() or "НЕ копия" in user


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


def test_enforce_rejects_full_quote_as_answer() -> None:
    quote = (
        "Если предоставлена полная информация, Координатор департамента назначает РП "
        "в соответствии с итоговым Расчётом проекта в течение 1 рабочего дня."
    )
    assert looks_like_regulation_copy(quote, quote)
    short = enforce_short_paraphrase(quote, query="В какой срок назначается РП?", quote=quote)
    assert short != quote
    assert "назначает РП в соответствии" not in short
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
        query="В какой срок назначается РП?",
        glossary=glossary,
    )
    lines = text.splitlines()
    assert lines[0].startswith("Ответ:")
    assert "РП (Руководитель проекта)" in lines[0]
    assert "**" not in lines[0]
    assert "п. 2.7" not in lines[0]
    assert lines[1].startswith("Источник:")
    assert lines[1].endswith("п. 2.7.")
    assert "назначает РП в соответствии" not in lines[1]
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
    assert "юридических лиц компании" in first.lower()
    assert "Источник:" in answer and "п. 9.5" in answer
    assert "Цитата:" in answer
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
    assert "подписывают" not in first.lower()
