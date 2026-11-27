"""
ANCHOR: app.application.dialogue.answer_format
PURPOSE: Human-readable grounded answer shape (Ответ / Источник / Цитата).
Dependencies: text_util; allowed_topics for system prompt
CRITICAL: Источник/Цитата must come from grounded citations — never invent.
DO:
- Short direct Ответ; authoritative Источник + Цитата from retrieval
- Adapt RCTIOSE priorities without tool-calling or user-visible CoT
DONT:
- Dump raw regulation prose as the only user-facing body
- Duplicate long citation UI noise beyond the three-line template
"""

from __future__ import annotations

import re

from app.application.text_util import (
    complete_sentences,
    cut_before_next_clause,
    strip_think_blocks,
    truncate_at_sentence,
)
from app.domain.allowed_topics import format_topics_for_prompt

_ANSWER_LINE_RE = re.compile(
    r"(?im)^\s*(?:\*\*)?ответ(?:\*\*)?\s*:\s*(.+?)\s*$"
)
_SOURCE_BLOCK_RE = re.compile(
    r"(?is)^\s*(?:\*\*)?источник(?:\*\*)?\s*:.*$"
)
_QUOTE_BLOCK_RE = re.compile(
    r"(?is)^\s*(?:\*\*)?цитата(?:\*\*)?\s*:.*$"
)
_QUESTIONS_BLOCK_RE = re.compile(
    r"(?is)^\s*(?:\*\*)?вопросы\s+и\s+уточнения(?:\*\*)?\s*:.*$"
)


def build_answer_system_prompt(topics_block: str | None = None) -> str:
    """
    RCTIOSE-adapted system prompt: retrieve already done; strip think; ALLOWED_TOPICS.
    """
    topics = (topics_block or "").strip() or format_topics_for_prompt(None)
    return (
        "Ты — ИИ-ассистент системного аналитика и эксперт по корпоративным знаниям.\n"
        "Специализация: точные ответы из внутренних регламентов с кратким ответом, "
        "источником и дословной цитатой.\n"
        "Стиль: точный, структурированный, фактологический, без воды и домыслов.\n"
        "Аудитория: сотрудники, руководители проектов, координаторы, аудиторы.\n"
        "\n"
        "Домен (in-domain topics):\n"
        f"{topics}\n"
        "\n"
        "Поиск по базе УЖЕ выполнен — passages ниже даны системой. "
        "Не вызывай инструменты и не выдумывай документы, пункты или цитаты.\n"
        "Не пиши блоки <think>/<thinking> и не рассуждай вслух — только финальный ответ.\n"
        "\n"
        "Приоритеты (от высшего к низшему):\n"
        "1) Точность и строгое соответствие passages (запрет галлюцинаций).\n"
        "2) Безопасность (маскируй ПДн как [ФИО] / [КОНТАКТ]).\n"
        "3) Структура Ответ – Источник – Цитата.\n"
        "4) Краткость и ясность.\n"
        "\n"
        "Отвечай ТОЛЬКО по passages, на русском. Если passages не подтверждают ответ — "
        "верни ровно UNSUPPORTED.\n"
        "\n"
        "Формат выхода (ровно три строки, без преамбулы):\n"
        "Ответ: <один короткий прямой ответ на вопрос>\n"
        "Источник: «<название документа>», п. <пункт/раздел из passages>\n"
        "Цитата: «<дословный фрагмент из passages, подтверждающий ответ>»\n"
        "\n"
        "Не добавляй «Вопросы и уточнения» для уверенного grounded-ответа.\n"
        "Не дублируй длинные куски регламента в «Ответ» — там только суть.\n"
        "\n"
        "Хороший пример:\n"
        "Ответ: В течение одного рабочего дня при наличии полной информации.\n"
        "Источник: «Проектная деятельность Дирекции ИБ.docx», п. 2.7.\n"
        "Цитата: «Если предоставлена полная информация, Координатор департамента "
        "назначает РП в соответствии с итоговым Расчётом проекта в течение 1 рабочего дня.»\n"
        "\n"
        "Плохой пример (запрещено): «Обычно РП назначается за 2-3 дня» без источника и цитаты.\n"
    )


def build_answer_user_prompt(*, question: str, passages: list[str]) -> str:
    joined = "\n".join(passages)
    return (
        f"Question: {question}\n"
        "Passages (grounded retrieval — cite only these):\n"
        f"{joined}\n"
        "\n"
        "Сформулируй краткий человекочитаемый ответ в формате Ответ / Источник / Цитата."
    )


def extract_answer_body(text: str) -> str:
    """Take the human «Ответ:» line; else return cleaned prose without source/quote lines."""
    cleaned = strip_think_blocks(text or "")
    if not cleaned:
        return ""
    for line in cleaned.splitlines():
        m = _ANSWER_LINE_RE.match(line.strip())
        if m:
            return m.group(1).strip().strip("*").strip()
    # Drop trailing Источник/Цитата/Вопросы blocks if model mixed formats.
    kept: list[str] = []
    for line in cleaned.splitlines():
        s = line.strip()
        if not s:
            if kept:
                break
            continue
        if _SOURCE_BLOCK_RE.match(s) or _QUOTE_BLOCK_RE.match(s) or _QUESTIONS_BLOCK_RE.match(s):
            break
        kept.append(s)
    return cut_before_next_clause(" ".join(kept).strip())


def format_source_line(*, document_title: str, locator: str | None = None) -> str:
    title = (document_title or "").strip() or "Корпоративный регламент"
    loc = (locator or "").strip()
    # Locators often look like "2.7." or "п. 2.7" — normalize to «…», п. 2.7.
    loc = re.sub(r"^п(?:ункт)?\.?\s*", "", loc, flags=re.IGNORECASE).rstrip(".")
    if loc:
        return f"Источник: «{title}», п. {loc}."
    return f"Источник: «{title}»."


def format_quote_line(quote: str) -> str:
    q = cut_before_next_clause((quote or "").strip()).strip(" «»\"'")
    return f"Цитата: «{q}»"


def format_human_answer(
    *,
    answer: str,
    document_title: str,
    locator: str | None = None,
    quote: str,
) -> str:
    """Assemble the three-line body shown before the citations UI."""
    body = extract_answer_body(answer) or cut_before_next_clause(answer)
    body = complete_sentences(body, max_chars=400) if body else ""
    if not body:
        body = complete_sentences(quote or "", max_chars=400)
    body = body.strip()
    if not body:
        return ""
    if not body.lower().startswith("ответ:"):
        body = f"Ответ: {body}"
    return "\n".join(
        [
            body,
            format_source_line(document_title=document_title, locator=locator),
            format_quote_line(quote),
        ]
    )


def summary_from_answer(answer_text: str, max_len: int = 480) -> str:
    """
    Appeal summary: prefer the short Ответ line; fall back to sentence truncate.
    """
    cleaned = strip_think_blocks(answer_text or "")
    body = extract_answer_body(cleaned)
    if body:
        line = body if body.lower().startswith("ответ:") else f"Ответ: {body}"
        if len(line) <= max_len:
            return line
        return truncate_at_sentence(line, max_len)
    return truncate_at_sentence(cleaned, max_len)
