"""
ANCHOR: app.application.dialogue.answer_format
PURPOSE: Human-readable grounded answer shape (Ответ / Источник / Цитата).
Dependencies: text_util; allowed_topics; optional glossary
CRITICAL: Источник/Цитата must come from grounded citations — never invent.
DO:
- Short direct Ответ without clause numbers; ≠ full quote
- Authoritative Источник + Цитата from retrieval
- Expand known abbreviations in user-facing Ответ when glossary active
DONT:
- Dump raw regulation prose / point numbers as Ответ
- Set Ответ equal to Цитата
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from app.application.text_util import (
    complete_sentences,
    cut_before_next_clause,
    lexical_overlap,
    strip_think_blocks,
    truncate_at_sentence,
)
from app.domain.allowed_topics import format_topics_for_prompt

if TYPE_CHECKING:
    from app.domain.glossary import AbbreviationGlossary

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
_ACCORDING_TO_RE = re.compile(
    r"^Согласно\s+регламенту\s*«[^»]*»\s*:\s*",
    re.IGNORECASE,
)
_LEADING_CLAUSE_RE = re.compile(
    r"^(?:\*\*)?\d+(?:\.\d+)*\.?(?:\*\*)?\s+"
)
_INLINE_POINT_RE = re.compile(
    r"(?:,?\s*)?\bп(?:ункт)?\.?\s*\d+(?:\.\d+)*\.?\b",
    re.IGNORECASE,
)
_BOLD_CLAUSE_RE = re.compile(r"\*\*\d+(?:\.\d+)*\.?\*\*")
_MAX_ANSWER_CHARS = 180


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
        "Ответ: <очень короткий прямой ответ — обычно до 15 слов>\n"
        "Источник: «<название документа>», п. <пункт/раздел>\n"
        "Цитата: «<дословный фрагмент из passages>»\n"
        "\n"
        "Правила для поля «Ответ» (обязательно):\n"
        "- Это человекочитаемая суть, НЕ копия регламента и НЕ копия «Цитата».\n"
        "- ЗАПРЕЩЕНЫ номера пунктов/разделов (9.5, п. 2.7, **10.) и префикс "
        "«Согласно регламенту».\n"
        "- Раскрой известные аббревиатуры один раз: РП → РП (Руководитель проекта), "
        "ДИБ → ДИБ (Дирекция информационной безопасности).\n"
        "\n"
        "Хорошие примеры:\n"
        "Ответ: Уполномоченные представители юридических лиц Компании.\n"
        "Источник: «Пресейловая деятельность Дирекции ИБ», п. 9.5.\n"
        "Цитата: «Договоры на закупку подписывают уполномоченные представители "
        "юридических лиц Компании.»\n"
        "\n"
        "Ответ: В течение одного рабочего дня при наличии полной информации.\n"
        "Источник: «Проектная деятельность Дирекции ИБ.docx», п. 2.7.\n"
        "Цитата: «Если предоставлена полная информация, Координатор департамента "
        "назначает РП в соответствии с итоговым Расчётом проекта в течение 1 рабочего дня.»\n"
        "\n"
        "Плохие примеры (запрещено):\n"
        "- Ответ = длинный абзац из регламента с «**9.5.** …»\n"
        "- Ответ совпадает с Цитатой целиком\n"
        "- «Обычно РП назначается за 2-3 дня» без источника\n"
    )


def build_answer_user_prompt(*, question: str, passages: list[str]) -> str:
    joined = "\n".join(passages)
    return (
        f"Question: {question}\n"
        "Passages (grounded retrieval — cite only these):\n"
        f"{joined}\n"
        "\n"
        "Сформулируй краткий человекочитаемый ответ в формате Ответ / Источник / Цитата. "
        "В «Ответ» — только суть без номеров пунктов; не копируй цитату."
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


def strip_regulation_noise(text: str) -> str:
    """Remove clause numbers / «Согласно регламенту» noise from the Ответ body."""
    text = cut_before_next_clause(strip_think_blocks(text or ""))
    if not text:
        return ""
    # Drop leading "Ответ:" if present so cleaning applies to the body.
    prefixed = False
    low = text.lower()
    if low.startswith("ответ:"):
        text = text.split(":", 1)[1].strip()
        prefixed = True
    text = _ACCORDING_TO_RE.sub("", text).strip()
    text = _LEADING_CLAUSE_RE.sub("", text).strip()
    text = _BOLD_CLAUSE_RE.sub("", text)
    text = _INLINE_POINT_RE.sub("", text)
    text = re.sub(r"\s{2,}", " ", text).strip(" ,;")
    if prefixed and text:
        return f"Ответ: {text}"
    return text


def is_near_quote_duplicate(answer: str, quote: str) -> bool:
    """True when Ответ is essentially the full цитата (too long / near-copy)."""
    a = strip_regulation_noise(answer or "").lower().strip(" «»\"'.")
    q = cut_before_next_clause(quote or "").lower().strip(" «»\"'.")
    if not a or not q:
        return False
    if a == q:
        return True
    # Short noun-phrase answers that appear inside the quote are fine.
    if len(a) <= 80 and a in q:
        return False
    if a in q or q in a:
        return len(a) > 80
    return lexical_overlap(a, q) >= 0.85 and len(a) > 100


def normalize_short_answer(text: str, *, quote: str = "", max_chars: int = _MAX_ANSWER_CHARS) -> str:
    """Produce a short human Ответ body (no clause dump, not a full quote copy)."""
    body = strip_regulation_noise(extract_answer_body(text) or text)
    if body.lower().startswith("ответ:"):
        body = body.split(":", 1)[1].strip()
    body = complete_sentences(body, max_chars=max_chars) if body else ""
    if body and is_near_quote_duplicate(body, quote):
        # Prefer a shorter lead phrase rather than reprinting the quote.
        body = truncate_at_sentence(body, min(max_chars, 100))
        if is_near_quote_duplicate(body, quote):
            body = ""
    return body.strip()


def format_source_line(*, document_title: str, locator: str | None = None) -> str:
    title = (document_title or "").strip() or "Корпоративный регламент"
    loc = (locator or "").strip()
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
    glossary: AbbreviationGlossary | None = None,
) -> str:
    """Assemble the three-line body shown before the citations UI."""
    body = normalize_short_answer(answer, quote=quote)
    if not body:
        # Last resort: short cleaned fragment of the supporting clause — never full quote dump.
        body = normalize_short_answer(quote or "", quote="")
        if is_near_quote_duplicate(body, quote):
            body = truncate_at_sentence(strip_regulation_noise(quote or ""), 90)
    body = body.strip()
    if not body:
        return ""
    if glossary is not None:
        body = glossary.expand_for_display(body)
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
        body = strip_regulation_noise(body)
        if body.lower().startswith("ответ:"):
            body = body.split(":", 1)[1].strip()
        line = f"Ответ: {body}" if body else ""
        if line and len(line) <= max_len:
            return line
        if line:
            return truncate_at_sentence(line, max_len)
    return truncate_at_sentence(cleaned, max_len)
