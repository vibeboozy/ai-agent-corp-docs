"""
ANCHOR: app.domain.glossary
PURPOSE: Configurable abbreviation glossary for query expansion + ingest metadata.
Dependencies: re; Settings ABBREVIATION_*
DO:
- Expand query abbreviations before hybrid retrieval
- Optionally tag chunks with matched abbreviations at ingest
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
                if key.casefold() == raw.casefold():
                    found[key] = exp
                    break
        return found

    def expand(self, text: str) -> str:
        """
        Append expansions for abbreviations found in text (query expansion).

        Original text is preserved; expansions are appended so sparse/dense
        both see the full form.
        """
        if not self.expand_query or not text:
            return text
        matches = self.find_matches(text)
        if not matches:
            return text
        extras = [f"{abbr} ({exp})" for abbr, exp in matches.items() if exp.lower() not in text.lower()]
        if not extras:
            return text
        return f"{text} " + " ".join(extras)

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
