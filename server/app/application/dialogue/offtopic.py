"""
ANCHOR: app.application.dialogue.offtopic
PURPOSE: Detect off-topic chitchat; refuse politely (regulation Q&A only).
Dependencies: re, unicodedata
DO:
- Catch clear non-regulation asks (time, weather, jokes, identity)
DONT:
- Refuse regulation process questions that happen to mention time/weather as context
"""

from __future__ import annotations

import re
import unicodedata

# Standalone chitchat / unsupported asks (whole-message or dominant intent).
_OFF_TOPIC_RE = re.compile(
    r"(?iu)^\s*(?:"
    r"сколько\s+(?:сейчас\s+)?времени"
    r"|который\s+час"
    r"|какое\s+(?:сегодня\s+)?(?:число|день)"
    r"|какая\s+(?:сегодня\s+)?погода"
    r"|расскажи\s+(?:анекдот|шутку|о\s+себе)"
    r"|как\s+дела"
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

# Soft cues that still look like regulation when combined with process nouns —
# used only to *avoid* false positives, not to detect off-topic alone.
_REGULATION_CUE_RE = re.compile(
    r"(?iu)\b(?:"
    r"регламент|процесс|проект|договор|закупк|отч[её]тн|подряд|"
    r"ответствен|подписыв|согласу|утвержд|поставк|отпуск|бренд"
    r")\b"
)

OFF_TOPIC_REFUSAL_RU = (
    "Этот вопрос не поддерживается. Я отвечаю только на вопросы по "
    "корпоративным регламентам и процессам. Переформулируйте запрос "
    "в терминах регламента (роль, процесс, документ)."
)


def _normalize(text: str) -> str:
    folded = unicodedata.normalize("NFKC", text or "")
    return folded.replace("ё", "е").replace("Ё", "Е").strip()


def is_off_topic(user_message: str, history: list[str] | None = None) -> bool:
    """
    True when the turn is unsupported chitchat (e.g. «Сколько времени»).

    History is ignored for detection — off-topic is judged on the current message.
    Messages that clearly name a regulation process are never refused here.
    """
    _ = history
    msg = _normalize(user_message)
    if not msg:
        return False
    if _REGULATION_CUE_RE.search(msg):
        return False
    return bool(_OFF_TOPIC_RE.match(msg))
