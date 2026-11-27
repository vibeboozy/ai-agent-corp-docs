"""
ANCHOR: app.domain.allowed_topics
PURPOSE: In-domain topic labels + domain mode for gate / classify / answer prompts.
Dependencies: stdlib only; Settings DIALOGUE_DOMAIN_MODE
DO:
- Always include corporate regulations as the core in-domain topic
- Resolve regs_only vs regs_legal from explicit DIALOGUE_DOMAIN_MODE
- Bake Конституция РФ + Трудовой кодекс РФ topics when mode is regs_legal
DONT:
- Parse free-form ALLOWED_TOPICS lists (removed)
- Treat weather/chitchat as in-domain just because legal mode is on
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal


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


DomainMode = Literal["regs_only", "regs_legal"]

# Always in-domain.
CORE_ALLOWED_TOPIC = AllowedTopic(
    label="корпоративные регламенты и процессы",
    description=(
        "внутренние регламенты, роли, согласования, договоры, закупки, "
        "отчётность, отпуска, бренд"
    ),
)

# Baked extras for DIALOGUE_DOMAIN_MODE=regs_legal (ingest matching docs first).
LEGAL_BAKED_TOPICS: tuple[AllowedTopic, ...] = (
    AllowedTopic(
        label="Конституция РФ",
        description="основной закон РФ",
    ),
    AllowedTopic(
        label="Трудовой кодекс РФ",
        description="трудовые отношения",
    ),
)

_VALID_MODES: frozenset[str] = frozenset({"regs_only", "regs_legal"})


def _normalize(text: str) -> str:
    folded = unicodedata.normalize("NFKC", text or "")
    return folded.replace("ё", "е").replace("Ё", "Е").strip()


def normalize_domain_mode(raw: str | None) -> DomainMode:
    """
    Map env / caller text to regs_only | regs_legal.

    Unknown / empty values default to regs_only.
    """
    token = (raw or "").strip().lower().replace("-", "_")
    if token in ("regs_legal", "regs+legal", "legal"):
        return "regs_legal"
    return "regs_only"


def resolve_prompt_mode(mode: DomainMode | str | None = None) -> DomainMode:
    """Normalize explicit domain mode (not topic sniffing)."""
    if mode in _VALID_MODES:
        return mode  # type: ignore[return-value]
    return normalize_domain_mode(None if mode is None else str(mode))


def topics_for_mode(mode: DomainMode | str | None = None) -> list[AllowedTopic]:
    """Core corporate topic; + baked Конституция/ТК when regs_legal."""
    resolved = resolve_prompt_mode(mode)
    out = [CORE_ALLOWED_TOPIC]
    if resolved == "regs_legal":
        out.extend(LEGAL_BAKED_TOPICS)
    return out


def is_legal_mode(mode: DomainMode | str | None) -> bool:
    return resolve_prompt_mode(mode) == "regs_legal"


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
    True when the message names an *extra* in-domain topic label.

    Core corporate domain is covered by regulation-cue heuristics elsewhere;
    this only matches baked legal extras (and any non-core entries passed in).
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


# Alias kept for answer_format / tests naming.
PromptMode = DomainMode


def resolve_allowed_topics(mode: DomainMode | str | None = None) -> list[AllowedTopic]:
    """Resolve topic list for a domain mode (replaces ALLOWED_TOPICS parsing)."""
    return topics_for_mode(mode)
