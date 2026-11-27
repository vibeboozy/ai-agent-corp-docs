"""
ANCHOR: app.domain.allowed_topics
PURPOSE: Configurable in-domain topic labels for the off-topic / domain gate.
Dependencies: stdlib only; Settings ALLOWED_TOPICS
DO:
- Always include corporate regulations as the core in-domain topic
- Parse extra labels/descriptions from env for future corpora (e.g. Конституция РФ)
DONT:
- Treat weather/chitchat as in-domain just because ALLOWED_TOPICS is set
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class AllowedTopic:
    """One in-domain topic: short label + optional description for prompts."""

    label: str
    description: str = ""

    def prompt_line(self) -> str:
        label = self.label.strip()
        desc = self.description.strip()
        if desc:
            return f"- {label}: {desc}"
        return f"- {label}"


# Always in-domain; ALLOWED_TOPICS only *adds* further corpora after ingest.
CORE_ALLOWED_TOPIC = AllowedTopic(
    label="корпоративные регламенты и процессы",
    description=(
        "внутренние регламенты, роли, согласования, договоры, закупки, "
        "отчётность, отпуска, бренд"
    ),
)


def _normalize(text: str) -> str:
    folded = unicodedata.normalize("NFKC", text or "")
    return folded.replace("ё", "е").replace("Ё", "Е").strip()


def parse_allowed_topics(raw: str | None) -> list[AllowedTopic]:
    """
    Parse ALLOWED_TOPICS env text into topic entries.

    Separators: `;` `|` or newlines.
    Each entry: `Label` or `Label=description` or `Label: description`.
    """
    if not raw or not str(raw).strip():
        return []
    text = str(raw).replace("\r\n", "\n").replace("|", ";").replace("\n", ";")
    out: list[AllowedTopic] = []
    seen: set[str] = set()
    for part in text.split(";"):
        chunk = part.strip()
        if not chunk:
            continue
        label = chunk
        description = ""
        if "=" in chunk:
            label, description = chunk.split("=", 1)
        elif ":" in chunk:
            label, description = chunk.split(":", 1)
        label = label.strip()
        description = description.strip()
        if not label:
            continue
        key = _normalize(label).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(AllowedTopic(label=label, description=description))
    return out


def resolve_allowed_topics(raw: str | None = None) -> list[AllowedTopic]:
    """Core corporate topic plus any extras from ALLOWED_TOPICS."""
    extras = parse_allowed_topics(raw)
    core_key = _normalize(CORE_ALLOWED_TOPIC.label).lower()
    merged = [CORE_ALLOWED_TOPIC]
    for topic in extras:
        if _normalize(topic.label).lower() == core_key:
            continue
        merged.append(topic)
    return merged


def format_topics_for_prompt(topics: list[AllowedTopic] | None) -> str:
    """Bullet list for classify / answer system prompts."""
    items = topics or [CORE_ALLOWED_TOPIC]
    return "\n".join(t.prompt_line() for t in items)


def build_refusal_message(topics: list[AllowedTopic] | None = None) -> str:
    """User-facing RU refusal listing configured in-domain topics."""
    items = topics or [CORE_ALLOWED_TOPIC]
    labels = [t.label.strip() for t in items if t.label.strip()]
    if not labels:
        labels = [CORE_ALLOWED_TOPIC.label]
    if len(labels) == 1 and labels[0] == CORE_ALLOWED_TOPIC.label:
        # Preserve the historical corporate-only wording.
        return (
            "Этот вопрос не поддерживается. Я отвечаю только на вопросы по "
            "корпоративным регламентам и процессам. Переформулируйте запрос "
            "в терминах регламента (роль, процесс, документ)."
        )
    if len(labels) == 1:
        scope = labels[0]
    elif len(labels) == 2:
        scope = f"{labels[0]} и {labels[1]}"
    else:
        scope = ", ".join(labels[:-1]) + f" и {labels[-1]}"
    return (
        "Этот вопрос не поддерживается. Я отвечаю только на вопросы по темам: "
        f"{scope}. Переформулируйте запрос в терминах этих тем "
        "(роль, процесс, документ, норма)."
    )


def mentions_allowed_topic(
    user_message: str, topics: list[AllowedTopic] | None = None
) -> bool:
    """
    True when the message names an *extra* configured topic label.

    Core corporate domain is covered by regulation-cue heuristics elsewhere;
    this only matches ALLOWED_TOPICS extras (and any non-core entries passed in).
    """
    msg = _normalize(user_message).lower()
    if not msg:
        return False
    core_key = _normalize(CORE_ALLOWED_TOPIC.label).lower()
    for topic in topics or []:
        label = _normalize(topic.label)
        if not label or label.lower() == core_key:
            continue
        # Require a meaningful cue (≥3 chars) so tiny tokens do not open the gate.
        if len(label) < 3:
            continue
        if label.lower() in msg:
            return True
        # Also match significant tokens (e.g. «конституция» from «Конституция РФ»).
        for token in re.split(r"\s+", label):
            tok = token.strip(".,;:()[]«»\"'").lower()
            if len(tok) >= 5 and tok in msg:
                return True
    return False
