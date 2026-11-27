"""
ANCHOR: app.domain.glossary
PURPOSE: Configurable abbreviation glossary for query expansion + ingest metadata.
Dependencies: re; Settings ABBREVIATION_*
DO:
- Expand query abbreviations before hybrid retrieval
- Enrich ingest chunk TEXT (and metadata) so dense/sparse embeddings see expansions
DONT:
- Invent expansions not in the configured glossary
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

# Default corporate glossary (user-provided). Override via ABBREVIATION_GLOSSARY /
# ABBREVIATION_GLOSSARY_PATH.
DEFAULT_GLOSSARY_ENTRIES: tuple[tuple[str, str], ...] = (
    ("АМ", "Аккаунт-менеджер"),
    ("АП", "Администратор проекта"),
    ("БПМ", "Бизнес-процессы (Директор по БПМ)"),
    ("БИФ", "Бюджет внутреннего финансирования"),
    ("BDM", "Business Development Manager"),
    ("ЦК", "Центр компетенций"),
    ("ДРП", "Департамент работы с подрядчиками"),
    ("ДС", "Дополнительное соглашение"),
    ("ДЭБ", "Департамент экономической безопасности"),
    ("ДИБ", "Дирекция информационной безопасности"),
    ("ЗИП", "Запасные части, инструменты и принадлежности"),
    ("ЗНП", "Заявка на пресейл"),
    ("ЗНИ", "Запрос на изменение"),
    ("ЗП", "Заказ покупателя"),
    ("ГИП", "Главный инженер проекта"),
    ("КСУП", "Корпоративная система управления проектами"),
    ("ИСУП", "Корпоративная система управления проектами"),
    ("КП", "Коммерческое предложение"),
    ("КИ", "Кредитная история"),
    ("КС-2", "Акты о завершении работ (форма)"),
    ("КС-3", "Акты о завершении работ (форма)"),
    ("НМЦК", "Начальная максимальная цена контракта"),
    ("ОПЭ", "Окончательная приёмка/эксплуатация (Протокол ОПЭ)"),
    ("ПА", "Пресейл-архитектор"),
    ("ПГ", "План-график"),
    ("ПМИ", "Программа и методика испытаний"),
    ("ПСИ", "Приёмосдаточные испытания"),
    ("РП", "Руководитель проекта"),
    ("РСП", "Руководитель сервисного проекта"),
    ("РМ", "Ресурс-менеджер"),
    ("РТЗ", "Расчёт трудозатрат"),
    ("СБ", "Служба безопасности"),
    ("СРО", "Саморегулируемая организация"),
    ("SS", "Solution Sales"),
    ("SLA", "Service Level Agreement"),
    ("TSS", "Technical Solution Sales"),
    ("ТЗ", "Техническое задание"),
    ("ТКП", "Технико-коммерческое предложение"),
    ("ТМЦ", "Товарно-материальные ценности"),
    ("ТП", "Техническая поддержка"),
    ("УИБ", "Управление информационной безопасности"),
    ("УПД", "Универсальный передаточный документ"),
    ("ФТТ", "Функционально-технические требования"),
    ("ФОТ", "Фонд оплаты труда"),
    ("ФГ", "Функциональная группа"),
    ("HW", "Hardware (оборудование)"),
    ("ПО", "Программное обеспечение"),
    ("NDA", "Non-Disclosure Agreement (соглашение о неразглашении)"),
    ("RFI", "Request for Information"),
    ("FTE", "Full-Time Equivalent (полная занятость)"),
)


def parse_glossary_text(raw: str) -> dict[str, str]:
    """
    Parse `ABBR=expansion;ABBR2=expansion2` or newline/`|` separated pairs.

    Also accepts lines `ABBR expansion...` (first token = abbr).
    """
    out: dict[str, str] = {}
    if not raw or not raw.strip():
        return out
    # Normalize multi-line / semicolon / pipe separators into pieces.
    pieces = re.split(r"[\n;|]+", raw)
    for piece in pieces:
        piece = piece.strip()
        if not piece or piece.lower().startswith("glossar"):
            continue
        if "=" in piece:
            abbr, exp = piece.split("=", 1)
        elif "\t" in piece:
            abbr, exp = piece.split("\t", 1)
        else:
            parts = piece.split(None, 1)
            if len(parts) < 2:
                continue
            abbr, exp = parts[0], parts[1]
        abbr = abbr.strip().rstrip(",")
        exp = exp.strip()
        if not abbr or not exp:
            continue
        # Support "КСУП, ИСУП expansion" style left side.
        for token in re.split(r"\s*,\s*", abbr):
            token = token.strip()
            if token:
                out[token] = exp
    return out


def load_glossary_from_path(path: str | Path) -> dict[str, str]:
    p = Path(path)
    if not p.is_file():
        return {}
    return parse_glossary_text(p.read_text(encoding="utf-8"))


@dataclass
class AbbreviationGlossary:
    """Lookup + expand abbreviations for retrieval / ingest enrichment."""

    entries: dict[str, str] = field(default_factory=dict)
    expand_query: bool = True
    enrich_ingest: bool = True

    @classmethod
    def from_defaults(cls, **kwargs: object) -> AbbreviationGlossary:
        return cls(entries=dict(DEFAULT_GLOSSARY_ENTRIES), **kwargs)  # type: ignore[arg-type]

    def _matcher(self) -> re.Pattern[str] | None:
        if not self.entries:
            return None
        # Longest-first so КС-2 beats КС, КСУП beats КС.
        keys = sorted(self.entries.keys(), key=len, reverse=True)
        escaped = [re.escape(k) for k in keys]
        return re.compile(rf"(?iu)(?<!\w)({'|'.join(escaped)})(?!\w)")

    @staticmethod
    def _case_compatible(key: str, raw: str) -> bool:
        """
        Uppercase-only glossary keys (ПО, РП, ТЗ) must not match lowercase
        prepositions/particles (по, на, …).
        """
        if key.casefold() != raw.casefold():
            return False
        if key.isupper() and key.isalpha() and not any(ch.isupper() for ch in raw):
            return False
        return True

    def find_matches(self, text: str) -> dict[str, str]:
        """Return abbr→expansion for abbreviations present in text."""
        pat = self._matcher()
        if not pat or not text:
            return {}
        found: dict[str, str] = {}
        for m in pat.finditer(text):
            raw = m.group(1)
            # Preserve configured casing key.
            for key, exp in self.entries.items():
                if self._case_compatible(key, raw):
                    found[key] = exp
                    break
        return found

    def _append_expansions(self, text: str) -> str:
        """Append `ABBR (expansion)` for matches not already spelled out in text."""
        matches = self.find_matches(text)
        if not matches:
            return text
        extras = [
            f"{abbr} ({exp})"
            for abbr, exp in matches.items()
            if exp.lower() not in text.lower()
        ]
        if not extras:
            return text
        return f"{text} " + " ".join(extras)

    def expand(self, text: str) -> str:
        """
        Query expansion: append expansions so hybrid search sees full forms.

        Gated by `expand_query` (ABBREVIATION_EXPAND_QUERY).
        """
        if not self.expand_query or not text:
            return text
        return self._append_expansions(text)

    def display_enabled(self) -> bool:
        """True when any ABBREVIATION_* feature is on and glossary has entries."""
        return bool(self.entries) and (self.expand_query or self.enrich_ingest)

    def expand_for_display(self, text: str) -> str:
        """
        User-facing answer text: replace known abbr with ``ABBR (expansion)`` once.

        Active when query-expand or ingest-enrich is enabled (ABBREVIATION_*).
        Skips tokens whose expansion is already present in the text.
        """
        if not self.display_enabled() or not text:
            return text
        pat = self._matcher()
        if not pat:
            return text

        def _repl(match: re.Match[str]) -> str:
            raw = match.group(1)
            for key, exp in self.entries.items():
                if not self._case_compatible(key, raw):
                    continue
                if exp.lower() in text.lower():
                    return raw
                return f"{key} ({exp})"
            return raw

        return pat.sub(_repl, text)

    def enrich_text(self, text: str) -> str:
        """
        Ingest text enrichment: same append form as query expand.

        Mutates the chunk string before dense/sparse embed so Qdrant vectors
        include expansions. Gated by `enrich_ingest` (ABBREVIATION_ENRICH_INGEST).
        """
        if not self.enrich_ingest or not text:
            return text
        return self._append_expansions(text)

    def enrich_metadata(self, text: str, metadata: dict | None = None) -> dict:
        """Optionally attach matched abbreviations to chunk metadata."""
        base = dict(metadata or {})
        if not self.enrich_ingest:
            return base
        matches = self.find_matches(text)
        if matches:
            base["abbreviations"] = matches
        return base


@lru_cache
def build_glossary(
    *,
    glossary_text: str = "",
    glossary_path: str = "",
    expand_query: bool = True,
    enrich_ingest: bool = True,
    use_defaults: bool = True,
) -> AbbreviationGlossary:
    entries: dict[str, str] = {}
    if use_defaults:
        entries.update(DEFAULT_GLOSSARY_ENTRIES)
    if glossary_path:
        entries.update(load_glossary_from_path(glossary_path))
    if glossary_text:
        entries.update(parse_glossary_text(glossary_text))
    return AbbreviationGlossary(
        entries=entries,
        expand_query=expand_query,
        enrich_ingest=enrich_ingest,
    )
