"""
ANCHOR: app.application.dialogue.offtopic
PURPOSE: Detect off-topic chitchat; refuse politely (in-domain topics only).
Dependencies: re, unicodedata; domain.allowed_topics
DO:
- Catch clear non-domain asks (time, weather, jokes, identity)
- Treat configured ALLOWED_TOPICS cues as in-domain (not heuristic refuse)
DONT:
- Refuse regulation / allowed-topic questions that mention time/weather as context
"""

from __future__ import annotations

import re
import unicodedata
from typing import Sequence

from app.domain.allowed_topics import (
    AllowedTopic,
    CORE_ALLOWED_TOPIC,
    build_refusal_message,
    mentions_allowed_topic,
    resolve_allowed_topics,
)

# Standalone chitchat / unsupported asks (whole-message or dominant intent).
_OFF_TOPIC_RE = re.compile(
    r"(?iu)^\s*(?:"
    r"сколько\s+(?:сейчас\s+)?времени"
    r"|который\s+час"
    r"|какое\s+(?:сегодня\s+)?(?:число|день)"
    # «Какая погода?» / «Какая сегодня погода в Москве?»
    r"|какая\s+(?:сегодня\s+)?погода(?:\s+\S+){0,4}"
    r"|расскажи\s+(?:анекдот|шутку|о\s+себе)"
    r"|как\s+дела"
    # Cooking / lifestyle out of regs (golden GS-15).
    r"|как\s+приготовить\s+\S+"
    r"|привет(?:\s*,?\s*как\s+дела)?"
    r"|hello|hi\b|hey\b"
    r"|who\s+are\s+you"
    r"|what\s+time\s+is\s+it"
    r"|what'?s\s+the\s+weather"
    r"|tell\s+me\s+a\s+joke"
    r"|спой\s+песн"
    r"|нарисуй"
    r")\s*[?.!]?\s*$"
)

# Named external legal corpora — refuse unless listed in ALLOWED_TOPICS extras.
_EXTERNAL_CORPUS_RE = re.compile(
    r"(?iu)\b(?:"
    r"конституци\w*"
    r"|трудов(?:ой|ого|ому|ым)\s+кодекс\w*"
    r"|гражданск\w*\s+кодекс\w*"
    r"|уголовн\w*\s+кодекс\w*"
    r")\b"
)

# Soft cues that still look like corporate regulation when combined with process nouns —
# used only to *avoid* false positives, not to detect off-topic alone.
_REGULATION_CUE_RE = re.compile(
    r"(?iu)\b(?:"
    r"регламент|процесс|проект|договор|закупк|отч[её]тн|подряд|"
    r"ответствен|подписыв|согласу|утвержд|поставк|отпуск|бренд"
    r")\b"
)

# Default refusal (corporate-only); prefer build_refusal_message(allowed_topics) at runtime.
OFF_TOPIC_REFUSAL_RU = build_refusal_message([CORE_ALLOWED_TOPIC])


def _normalize(text: str) -> str:
    folded = unicodedata.normalize("NFKC", text or "")
    return folded.replace("ё", "е").replace("Ё", "Е").strip()


def is_supported_domain(
    user_message: str,
    allowed_topics: Sequence[AllowedTopic] | None = None,
) -> bool:
    """True when the message cues corporate regs or a configured allowed topic."""
    msg = _normalize(user_message)
    if not msg:
        return False
    topics = list(allowed_topics) if allowed_topics is not None else resolve_allowed_topics()
    # External corpora only count as in-domain when listed in ALLOWED_TOPICS.
    if _EXTERNAL_CORPUS_RE.search(msg):
        return mentions_allowed_topic(msg, topics)
    if _REGULATION_CUE_RE.search(msg):
        return True
    return mentions_allowed_topic(msg, list(topics))


def names_disallowed_external_topic(
    user_message: str,
    allowed_topics: Sequence[AllowedTopic] | None = None,
) -> bool:
    """
    True when the ask names Конституция/кодексы that are *not* in ALLOWED_TOPICS.

    Default corporate-only allowlist → Конституция РФ is off-topic (GS-16).
    """
    msg = _normalize(user_message)
    if not msg or not _EXTERNAL_CORPUS_RE.search(msg):
        return False
    topics = list(allowed_topics) if allowed_topics is not None else resolve_allowed_topics()
    return not mentions_allowed_topic(msg, topics)


def is_off_topic(
    user_message: str,
    history: list[str] | None = None,
    *,
    allowed_topics: Sequence[AllowedTopic] | None = None,
) -> bool:
    """
    True when the turn is unsupported chitchat (e.g. «Сколько времени»).

    History is ignored for detection — off-topic is judged on the current message.
    Messages that clearly name a regulation process or allowed topic are never refused here.
    Clear chitchat patterns (weather/time/jokes) stay refused even if ALLOWED_TOPICS is set.
    Named external corpora (Конституция / кодексы) refuse unless in ALLOWED_TOPICS.
    """
    _ = history
    msg = _normalize(user_message)
    if not msg:
        return False
    topics = list(allowed_topics) if allowed_topics is not None else resolve_allowed_topics()
    # In-domain cues win over bare chitchat patterns (e.g. time windows in processes).
    if is_supported_domain(msg, allowed_topics=topics):
        return False
    # Конституция / ТК / etc. without ALLOWED_TOPICS → refuse (do not retrieve junk regs).
    if names_disallowed_external_topic(msg, allowed_topics=topics):
        return True
    # Explicit chitchat → refuse before retrieve (retrieval gate).
    return bool(_OFF_TOPIC_RE.match(msg))
