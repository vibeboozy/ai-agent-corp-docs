"""
ANCHOR: app.application.dialogue.answer_format
PURPOSE: Human-readable grounded answer shape (Ответ / Источник / Цитата).
Dependencies: text_util; allowed_topics; optional glossary
CRITICAL: Источник/Цитата must come from grounded citations — never invent.
DO:
- Ответ = one short WHO/WHAT/WHEN paraphrase (never regulation dump / mid-clause cut)
- Источник = document title + п. N only (never a full sentence)
- Expand known abbreviations in Ответ when glossary active
- Compose answer system prompt: shared regs base + optional legal addendum
DONT:
- Copy regulation wording into Ответ
- Truncate mid-clause with ellipsis as the user-facing answer
- Put clause body text into the Источник line
- Mention ТК РФ / Конституция in regs-only mode
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Sequence

from app.application.text_util import (
    cut_before_next_clause,
    lexical_overlap,
    strip_think_blocks,
    tokenize,
    truncate_at_sentence,
)
from app.domain.allowed_topics import (
    AllowedTopic,
    format_topics_for_prompt,
    includes_legal_topics,
    resolve_prompt_mode,
)

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
_LOCATOR_NUM_RE = re.compile(
    r"^(?:\*\*)?(\d+(?:\.\d+)*)\.?(?:\*\*)?(?:\s|$)"
)
_MAX_ANSWER_CHARS = 110
_MAX_ANSWER_WORDS = 14
_HANGING_TAIL_RE = re.compile(
    r"(?i)(?:\b(?:от|для|по|на|с|из|и|или|кроме|при|без|через|под|над|между|а|но|что|как|в)\b"
    r"|[,:;–—\-]|…|\.\.\.)$"
)
# WHO active verbs with both sides (Russian may be SVO or OVS).
_WHO_ACTIVE_BOTH_RE = re.compile(
    r"(?is)([^\n.]+?)\s+"
    r"(назначает|ведёт|подписывает|утверждает|согласовывает)\s+"
    r"([^\n.]+?)(?:\.|$)"
)
# WHO: agent AFTER (отвечает Y / заключаются от Y / подписывают Y)
_WHO_AGENT_AFTER_RES = (
    re.compile(
        r"(?is)отвечает\s+(.+?)(?:\.|$)",
    ),
    re.compile(
        r"(?is)заключа(?:ются|ется)\s+от\s+(.+?)(?:\.|$)",
    ),
    re.compile(
        r"(?is)подписывают\s+(.+?)(?:\.|$)",
    ),
    re.compile(
        r"(?is)является\s+(.+?)(?:\.|$)",
    ),
)
_ROLE_LIKE_RE = re.compile(
    r"(?i)^(?:"
    r"[A-ZА-ЯЁ]{2,6}"
    r"|(?:руководитель|координатор|менеджер|директор|администратор|инженер|уполномоченн|"
    r"юридическ)"
    r")"
)
_WHEN_EXTRACT_RES = (
    re.compile(
        r"(?is)(?:в\s+течение|не\s+позднее)\s+(.+?)(?:\.|$)",
    ),
)
_REGULATION_LEAK_RES = (
    re.compile(r"(?i)\bзаключа(?:ются|ется|ть)\b"),
    re.compile(r"(?i)\bподписыва(?:ют|ет|ть)\b"),
    re.compile(r"(?i)\bназначает\b"),
    re.compile(r"(?i)\bкроме\b"),
    re.compile(r"(?i)\bперепродаж"),
    re.compile(r"(?i)\bсубподряд"),
    re.compile(r"(?i)\bэлектронной\s+почт"),
)
# Object-like dumps mistaken for the WHO answer (verb object, not subject).
_WHO_OBJECT_NOISE_RE = re.compile(
    r"(?i)^(задачи|договоры|работы|заявки|документы|отчётность|сроки)\b"
)


def _answer_prompt_base(*, topics_block: str) -> str:
    """Shared RCTIOSE-adapted base (regs + learned). No ТК/Конституция mentions."""
    return (
        "Ты — ИИ-агент по поиску ответов в корпоративных документах.\n"
        "Специализация: корпоративные регламенты (проектная / пресейловая деятельность "
        "Дирекции ИБ, ДБРЦТ, Технической дирекции) и подтверждённые экспертные ответы "
        "из базы знаний.\n"
        "Стиль: точный, структурированный, краткий, с обязательной ссылкой на источник "
        "и дословной цитатой. Уровень: senior-ассистент по корпоративной базе знаний.\n"
        "Главное правило: если в документах нет прямого ответа — не выдумывай. "
        "Система уже умеет уточнять (clarify) и эскалировать в службу качества (escalate); "
        "ты для grounded-ответа либо даёшь подтверждённый факт, либо UNSUPPORTED.\n"
        "\n"
        "Домен (in-domain topics):\n"
        f"{topics_block}\n"
        "\n"
        "Архитектура (инструменты уже отработали — НЕ вызывай tool calls):\n"
        "- retrieve / hybrid Qdrant: passages ниже уже найдены (корпоративные + learned).\n"
        "- learned (get_knowledge_base_answer): подтверждённый экспертный ответ может быть "
        "среди passages (source=learned) — используй его с привязкой к регламенту.\n"
        "- clarify (ask_user) и escalate (create_quality_request) — отдельные узлы графа; "
        "для этого шага не пиши список уточнений и не оформляй обращение.\n"
        "Не выдумывай документы, пункты или цитаты. Не пиши <think>/<thinking> — "
        "только финальный ответ.\n"
        "\n"
        "Приоритеты: безопасность/PII > точность и корректность источника > "
        "однозначность > эскалация при отсутствии факта > краткость.\n"
        "\n"
        "Правила поведения:\n"
        "- Однозначный вопрос + факт в passages → краткий Ответ + Источник + Цитата.\n"
        "- Неоднозначность (разные сроки по подразделениям / тип заявки неясен) → "
        "UNSUPPORTED (граф уйдёт в clarify/escalate). Не выбирай срок произвольно.\n"
        "- Нет прямого ответа / ложная предпосылка без опровергающей цитаты → UNSUPPORTED.\n"
        "- Ложная предпосылка, которую passages опровергают → дай верный факт + источник + цитату.\n"
        "- Частичный ответ: ответь только на подтверждённую часть; иначе UNSUPPORTED.\n"
        "- Противоречие источников без однозначного выбора → UNSUPPORTED.\n"
        "- Не подменяй корпоративный регламент общими знаниями.\n"
        "- Диалог: учитывай контекст follow-up («А в какой срок?»), но не переноси "
        "срок/подразделение, если новый вопрос явно про другое.\n"
        "- PII: маскируй как [ИМЯ], [EMAIL], [ТЕЛЕФОН], [НОМЕР_КАРТЫ], [АДРЕС].\n"
        "\n"
        "Формат выхода (ровно три строки):\n"
        "Ответ: <одна короткая фраза-парафраз: кто / что / когда — своими словами>\n"
        "Источник: «<название документа>», п. <только номер, например 9.5>\n"
        "Цитата: «<дословный фрагмент из passages>»\n"
        "\n"
        "Для learned/экспертного ответа Источник: подтверждённый экспертный ответ, "
        "привязанный к «<регламент>» (если passages это показывают).\n"
        "\n"
        "ЖЁСТКИЕ правила для «Ответ»:\n"
        "- Ровно одна короткая фраза (обычно ≤ 8–14 слов), WHO/WHAT/WHEN.\n"
        "- ЗАПРЕЩЕНО копировать формулировку регламента / цитаты.\n"
        "- ЗАПРЕЩЕНО обрезать фразу посередине (никаких «…заключаются от…»).\n"
        "- ЗАПРЕЩЕНЫ номера пунктов и «Согласно регламенту» в Ответ.\n"
        "- В «Источник» только документ и п. N — без текста пункта.\n"
        "- Раскрой аббревиатуры один раз: РП → РП (Руководитель проекта).\n"
        "\n"
        "Хороший пример (WHEN):\n"
        "Вопрос: В какой срок назначается РП в Дирекции ИБ при полной информации?\n"
        "Ответ: В течение одного рабочего дня при наличии полной информации.\n"
        "Источник: «Проектная деятельность Дирекции ИБ.docx», п. 2.7.\n"
        "Цитата: «Если предоставлена полная информация, Координатор департамента "
        "назначает РП в соответствии с итоговым Расчётом проекта в течение 1 рабочего дня.»\n"
        "\n"
        "Хороший пример (WHO):\n"
        "Вопрос: Кто подписывает договоры на закупку?\n"
        "Ответ: Юридические лица Компании.\n"
        "Источник: «Пресейловая деятельность Дирекции ИБ», п. 9.5.\n"
        "Цитата: «Все субподрядные договоры по ИБ проектам, кроме перепродажи "
        "вендорских сервисов, заключаются от юридических лиц Компании.»\n"
        "\n"
        "Хороший пример (ложная предпосылка):\n"
        "Вопрос: Почему РП назначается за 10 рабочих дней при полной информации?\n"
        "Ответ: Срок составляет один рабочий день при полной информации.\n"
        "Источник: «Проектная деятельность Дирекции ИБ.docx», п. 2.7.\n"
        "Цитата: «…назначает РП … в течение 1 рабочего дня.»\n"
        "\n"
        "Плохо (запрещено):\n"
        "- Выдуманные сроки («обычно за 3–5 дней») без цитаты.\n"
        "- Копировать «Все субподрядные договоры… заключаются от…» в Ответ "
        "или обрезать на «заключаются от…».\n"
        "- Смешивать разные документы в одной цитате.\n"
        "\n"
        "Чек-лист: цитата подтверждает Ответ; документ/пункт верны; нет выдуманных "
        "сроков/статусов; неоднозначность → UNSUPPORTED.\n"
        "Если passages не подтверждают ответ — верни ровно UNSUPPORTED.\n"
        "Лучше UNSUPPORTED (clarify/escalate), чем красивый недостоверный ответ.\n"
    )


def _answer_prompt_legal_addendum() -> str:
    """Optional block when ALLOWED_TOPICS includes Конституция РФ / ТК РФ."""
    return (
        "\n"
        "=== Дополнение: законодательство РФ (режим regs+legal) ===\n"
        "Дополнительная специализация: Трудовой кодекс РФ и Конституция РФ "
        "(только если соответствующие passages присутствуют).\n"
        "\n"
        "Правила для правовых вопросов:\n"
        "- Отвечай только по passages закона; не подменяй закон корпоративным регламентом "
        "и наоборот.\n"
        "- Смешанный вопрос (регламент + закон): отвечай по частям отдельно, "
        "не смешивай источники в одной цитате.\n"
        "- Не смешивай ТК РФ и Конституцию в одной цитате.\n"
        "- Укажи закон, статью/часть в Источнике.\n"
        "\n"
        "Формат для законодательства (те же три строки):\n"
        "Ответ: <краткий факт>\n"
        "Источник: <Название закона>, ст. <N>[, ч. <N>]\n"
        "Цитата: «<дословный фрагмент>»\n"
        "\n"
        "Пример (закон):\n"
        "Вопрос: Какова нормальная продолжительность рабочей недели?\n"
        "Ответ: Не более 40 часов в неделю.\n"
        "Источник: Трудовой кодекс Российской Федерации, ст. 91.\n"
        "Цитата: «Нормальная продолжительность рабочего времени не может превышать "
        "40 часов в неделю.»\n"
        "\n"
        "Плохо: смешивать ТК РФ и корпоративный регламент в одной цитате.\n"
    )


def build_answer_system_prompt(
    topics_block: str | None = None,
    *,
    topics: Sequence[AllowedTopic] | None = None,
    include_legal: bool | None = None,
) -> str:
    """
    RCTIOSE-adapted system prompt composed from shared base + optional legal addendum.

    Mode:
    - regs_only: corporate regs + learned; no ТК/Конституция wording
    - regs_legal: when ALLOWED_TOPICS includes those corpora (or include_legal=True)

    Retrieval already ran; no fake tools; clarify/escalate live in the graph.
    """
    topic_list = list(topics) if topics is not None else None
    block = (topics_block or "").strip()
    if not block:
        block = format_topics_for_prompt(topic_list)
    if include_legal is None:
        legal = includes_legal_topics(topic_list) if topic_list is not None else False
    else:
        legal = bool(include_legal)
    prompt = _answer_prompt_base(topics_block=block)
    if legal:
        prompt = prompt + _answer_prompt_legal_addendum()
    return prompt


def answer_prompt_mode(
    topics: Sequence[AllowedTopic] | None = None,
    *,
    include_legal: bool | None = None,
) -> str:
    """Expose regs_only | regs_legal for tests / audit."""
    if include_legal is not None:
        return "regs_legal" if include_legal else "regs_only"
    return resolve_prompt_mode(list(topics) if topics is not None else None)


def build_answer_user_prompt(*, question: str, passages: list[str]) -> str:
    joined = "\n".join(passages)
    return (
        f"Question: {question}\n"
        "Passages (grounded retrieval — cite only these):\n"
        f"{joined}\n"
        "\n"
        "Ответ — короткий парафраз (кто/что/когда), НЕ копия регламента и НЕ обрезка цитаты. "
        "Источник — только документ + п. N."
    )


def build_paraphrase_repair_prompt(*, question: str, quote: str, bad_answer: str) -> str:
    """Second-pass prompt when the model dumped regulation wording."""
    return (
        f"Question: {question}\n"
        f"Supporting quote: {quote}\n"
        f"Bad answer (do not reuse wording): {bad_answer}\n"
        "\n"
        "Rewrite ONLY the Ответ line as one short WHO/WHAT/WHEN paraphrase in Russian. "
        "For WHO questions keep the role/subject (e.g. РП), never the verb object "
        "(не «задачи сотрудникам…»). Do not copy the quote. Do not truncate mid-clause. "
        "Reply with a single line: Ответ: <paraphrase>"
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
    prefixed = False
    if text.lower().startswith("ответ:"):
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


def normalize_locator(locator: str | None) -> str | None:
    """Keep only the point number (e.g. 9.5) — never the clause sentence."""
    loc = (locator or "").strip()
    if not loc:
        return None
    loc = re.sub(r"^п(?:ункт)?\.?\s*", "", loc, flags=re.IGNORECASE).strip()
    m = _LOCATOR_NUM_RE.match(loc)
    if m:
        return m.group(1)
    # Bare number without trailing prose.
    if re.fullmatch(r"\d+(?:\.\d+)*", loc.rstrip(".")):
        return loc.rstrip(".")
    return None


def is_incomplete_answer(text: str) -> bool:
    """True when the answer looks mid-clause truncated."""
    t = (text or "").strip()
    if not t:
        return True
    if t.endswith("…") or t.endswith("..."):
        return True
    if _HANGING_TAIL_RE.search(t):
        return True
    # No terminal punctuation and ends mid-thought with a dangling preposition phrase.
    if not re.search(r"[.!?…»\"]\s*$", t) and len(tokenize(t)) >= 6:
        if re.search(r"(?i)\b(заключа|подпис|кроме|перепродаж)", t):
            return True
    return False


def looks_like_regulation_copy(answer: str, quote: str) -> bool:
    """True when Ответ copies regulation wording instead of paraphrasing."""
    a = strip_regulation_noise(answer or "").lower().strip(" «»\"'.")
    q = cut_before_next_clause(quote or "").lower().strip(" «»\"'.")
    if not a:
        return False
    words = tokenize(a)
    if len(a) > _MAX_ANSWER_CHARS or len(words) > _MAX_ANSWER_WORDS:
        return True
    if q:
        if a == q:
            return True
        # Short noun-phrase that appears inside the quote is a valid paraphrase core.
        if len(a) <= 80 and len(words) <= _MAX_ANSWER_WORDS and a in q:
            if not any(p.search(a) for p in _REGULATION_LEAK_RES):
                return False
        if a in q and len(a) > 40:
            return True
        if q in a and len(q) > 40:
            return True
        # High overlap + regulation-clause leaks / long substring ⇒ dumped wording.
        overlap = lexical_overlap(a, q)
        leaked = any(p.search(a) for p in _REGULATION_LEAK_RES)
        if overlap >= 0.55 and len(words) >= 6 and leaked:
            return True
        if overlap >= 0.8 and len(words) >= 8:
            return True
    # Long answer still carrying regulation verbs/leaks.
    if len(words) >= 6 and any(p.search(a) for p in _REGULATION_LEAK_RES):
        return True
    return False


_NOMINATIVE_FIXES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)^юридических\s+лиц\b"), "Юридические лица"),
    (re.compile(r"(?i)^уполномоченных\s+представителей\b"), "Уполномоченные представители"),
    (re.compile(r"(?i)^руководителя\s+проекта\b"), "Руководитель проекта"),
    (re.compile(r"(?i)^координатора\s+департамента\b"), "Координатор департамента"),
    (re.compile(r"(?i)^менеджера\s+по\s+поставке\b"), "Менеджер по поставке"),
)


def _capitalize_phrase(phrase: str) -> str:
    phrase = re.sub(r"\s{2,}", " ", (phrase or "").strip(" «»\"' ,;"))
    if not phrase:
        return ""
    # Drop trailing relative clauses that make it sentence-long.
    phrase = re.split(r",\s*(?:кроме|а также|в том числе)\b", phrase, maxsplit=1)[0].strip()
    # Keep short role abbreviations as-is (РП, АМ, ДИБ).
    if re.fullmatch(r"[A-ZА-ЯЁ]{1,6}", phrase):
        return phrase
    for pat, repl in _NOMINATIVE_FIXES:
        if pat.search(phrase):
            phrase = pat.sub(repl, phrase, count=1)
            break
    else:
        if phrase[0].isalpha():
            phrase = phrase[0].upper() + phrase[1:]
    return phrase


def _is_who_object_noise(phrase: str) -> bool:
    """True when extraction captured the verb object instead of the subject."""
    return bool(_WHO_OBJECT_NOISE_RE.match((phrase or "").strip()))


def _format_who_phrase(phrase: str) -> str:
    phrase = _capitalize_phrase(phrase)
    if not phrase:
        return ""
    if re.fullmatch(r"[A-ZА-ЯЁ]{1,6}", phrase):
        return phrase
    if not phrase.endswith((".", "!", "?")):
        phrase = phrase.rstrip(".") + "."
    return phrase


def _pick_who_side(left: str, right: str) -> str:
    """Choose role/subject side for active verbs (SVO vs OVS)."""
    candidates = [_capitalize_phrase(left), _capitalize_phrase(right)]
    # Prefer role-like side that is not object noise.
    for cand in candidates:
        if cand and _ROLE_LIKE_RE.match(cand) and not _is_who_object_noise(cand):
            return _format_who_phrase(cand)
    for cand in candidates:
        if cand and not _is_who_object_noise(cand) and not is_incomplete_answer(cand):
            if len(tokenize(cand)) <= 6:
                return _format_who_phrase(cand)
    return ""


def extract_short_paraphrase(query: str, passage: str) -> str:
    """
    Derive a short WHO/WHAT/WHEN paraphrase from the supporting passage.

    Used when the model dumps regulation text or truncates mid-clause.
    For WHO questions keep the role/subject (e.g. «РП»), never the verb object.
    """
    passage = strip_regulation_noise(cut_before_next_clause(passage or ""))
    if not passage:
        return ""
    q = (query or "").lower()
    who_ask = bool(re.search(r"\bкто\b", q))
    when_ask = bool(re.search(r"\b(срок|когда|в\s+какой\s+срок|как\s+быстро)\b", q))

    def _try_agent_after() -> str:
        for pat in _WHO_AGENT_AFTER_RES:
            m = pat.search(passage)
            if not m:
                continue
            phrase = _capitalize_phrase(m.group(1))
            if (
                phrase
                and not _is_who_object_noise(phrase)
                and not is_incomplete_answer(phrase)
                and not (
                    looks_like_regulation_copy(phrase, passage)
                    and len(tokenize(phrase)) > 4
                )
            ):
                if len(tokenize(phrase)) <= _MAX_ANSWER_WORDS and len(phrase) <= _MAX_ANSWER_CHARS:
                    return _format_who_phrase(phrase)
        return ""

    def _try_active_both() -> str:
        both = _WHO_ACTIVE_BOTH_RE.search(passage)
        if not both:
            return ""
        return _pick_who_side(both.group(1), both.group(3))

    def _try_when() -> str:
        for pat in _WHEN_EXTRACT_RES:
            m = pat.search(passage)
            if not m:
                continue
            phrase = _capitalize_phrase(m.group(1))
            if not phrase or is_incomplete_answer(phrase):
                continue
            if looks_like_regulation_copy(phrase, passage) and len(tokenize(phrase)) > 4:
                continue
            if len(tokenize(phrase)) <= _MAX_ANSWER_WORDS and len(phrase) <= _MAX_ANSWER_CHARS:
                return _format_who_phrase(phrase)
        return ""

    # Query only prioritizes order; always fall back across WHO/WHEN extractors so
    # clarify follow-ups ("Это про отчётность…") still get a role paraphrase.
    ordered: list = []
    if when_ask:
        ordered.extend([_try_when, _try_agent_after, _try_active_both])
    elif who_ask:
        ordered.extend([_try_active_both, _try_agent_after, _try_when])
    else:
        ordered.extend([_try_active_both, _try_agent_after, _try_when])

    for attempt in ordered:
        got = attempt()
        if got:
            return got
    return ""


def needs_paraphrase_repair(answer: str, *, quote: str = "") -> bool:
    """True when Ответ must be repaired (dump / incomplete / too long)."""
    body = strip_regulation_noise(extract_answer_body(answer) or answer)
    if body.lower().startswith("ответ:"):
        body = body.split(":", 1)[1].strip()
    if not body:
        return True
    return (
        is_incomplete_answer(body)
        or looks_like_regulation_copy(body, quote)
        or len(tokenize(body)) > _MAX_ANSWER_WORDS
        or len(body) > _MAX_ANSWER_CHARS
    )


def enforce_short_paraphrase(
    text: str,
    *,
    query: str = "",
    quote: str = "",
) -> str:
    """
    Hard-enforce a short paraphrase Ответ.

    Never returns mid-clause truncations or near-copies of the quote.
    """
    body = strip_regulation_noise(extract_answer_body(text) or text)
    if body.lower().startswith("ответ:"):
        body = body.split(":", 1)[1].strip()
    body = body.strip()

    if body and not needs_paraphrase_repair(body, quote=quote):
        if not re.search(r"[.!?…]\s*$", body):
            body = body.rstrip(".") + "."
        return body

    extracted = extract_short_paraphrase(query, quote or text)
    if extracted:
        return extracted
    # Do NOT fall back to truncating the quote — that produced «…заключаются от…».
    return ""


def format_source_line(*, document_title: str, locator: str | None = None) -> str:
    title = (document_title or "").strip() or "Корпоративный регламент"
    # Strip accidental «» wrapping so we don't double-wrap.
    title = title.strip(" «»\"'")
    point = normalize_locator(locator)
    if point:
        return f"Источник: «{title}», п. {point}."
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
    query: str = "",
    glossary: AbbreviationGlossary | None = None,
) -> str:
    """Assemble the three-line body shown before the citations UI."""
    body = enforce_short_paraphrase(answer, query=query, quote=quote)
    if not body:
        body = extract_short_paraphrase(query, quote)
    body = (body or "").strip()
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
    """Appeal summary: prefer the short Ответ line."""
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
