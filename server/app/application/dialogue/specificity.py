"""
ANCHOR: app.application.dialogue.specificity
PURPOSE: Conservative specificity helpers — prefer specific when role+topic named.
Dependencies: re, unicodedata
DO:
- Treat role-seeking + concrete topic as specific (override timid LLM labels)
- Combine history so short clarifications complete prior questions
- Normalize ё→е so orthography variants still match
DONT:
- Override true underspecified prompts (role without topic, or bare fragments)
"""

from __future__ import annotations

import re
import unicodedata

# Who/role-seeking cues (RU + light EN). Wide window so «Кто … отвечает …» matches.
_ROLE_RE = re.compile(
    r"(?iu)\bкто\b.{0,80}?\b(?:"
    r"отвечает|подписывает|согласует|утверждает|"
    r"нес[её]т\s+ответственность|ответствен(?:ен|на|ны|ность)?"
    r")\b"
    r"|\bwho\b.{0,80}?\b(?:is\s+responsible|signs|approves)\b"
)

# Concrete regulation topics — not bare «организация» alone.
_TOPIC_RE = re.compile(
    r"(?iu)\b(?:"
    r"отч[её]тн\w*"
    r"|закупк\w*"
    r"|подряд\w*"
    r"|отпуск\w*"
    r"|логотип\w*"
    r"|бренд(?:бук)?\w*"
    r"|договор\w*\s+на\s+\w+"
    r"|организаци\w+\s+отч[её]тн\w*"
    r"|проект\w*"
    r")\b"
)


def _normalize(text: str) -> str:
    """NFKC + ё→е so live LLM/user orthography does not break overrides."""
    folded = unicodedata.normalize("NFKC", text or "")
    return folded.replace("ё", "е").replace("Ё", "Е")


def looks_role_topic_specific(
    user_message: str, history: list[str] | None = None
) -> bool:
    """
    True when the turn (plus prior user turns) names a role-seeking ask AND a topic.

    Used to override timid underspecified/ambiguous LLM labels so grounded KB hits
    can answer instead of looping clarify.
    """
    parts = [*(history or []), user_message or ""]
    combined = _normalize(" ".join(p for p in parts if p).strip())
    if not combined:
        return False
    return bool(_ROLE_RE.search(combined) and _TOPIC_RE.search(combined))


def prefer_specific_label(
    label: str, user_message: str, history: list[str] | None = None
) -> str:
    """If LLM said underspecified/ambiguous but role+topic are present → specific."""
    normalized = (label or "underspecified").strip().lower()
    if normalized not in ("underspecified", "ambiguous"):
        return normalized
    if looks_role_topic_specific(user_message, history):
        return "specific"
    return normalized
