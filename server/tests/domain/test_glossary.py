"""
ANCHOR: tests.domain.test_glossary
PURPOSE: Abbreviation query expand + ingest text/metadata enrichment.
Dependencies: app.domain.glossary
"""

from __future__ import annotations

from app.domain.glossary import AbbreviationGlossary, parse_glossary_text


def test_parse_glossary_text_pairs() -> None:
    raw = "РП=Руководитель проекта;АМ=Аккаунт-менеджер\nТЗ Техническое задание"
    got = parse_glossary_text(raw)
    assert got["РП"] == "Руководитель проекта"
    assert got["АМ"] == "Аккаунт-менеджер"
    assert got["ТЗ"] == "Техническое задание"


def test_expand_appends_missing_expansions() -> None:
    g = AbbreviationGlossary.from_defaults()
    out = g.expand("Кто такой РП на проекте?")
    assert "РП" in out
    assert "Руководитель проекта" in out
    assert "РП (Руководитель проекта)" in out


def test_enrich_text_appends_for_ingest_embed() -> None:
    g = AbbreviationGlossary.from_defaults()
    out = g.enrich_text("За планирование поставок отвечает АМ.")
    assert "АМ (Аккаунт-менеджер)" in out
    assert out.startswith("За планирование поставок отвечает АМ.")


def test_enrich_metadata_tags_abbreviations() -> None:
    g = AbbreviationGlossary.from_defaults()
    meta = g.enrich_metadata("За планирование поставок отвечает АМ.")
    assert "abbreviations" in meta
    assert meta["abbreviations"]["АМ"] == "Аккаунт-менеджер"


def test_expand_disabled_noop() -> None:
    g = AbbreviationGlossary.from_defaults(expand_query=False)
    msg = "РП и АМ"
    assert g.expand(msg) == msg


def test_enrich_text_disabled_noop() -> None:
    g = AbbreviationGlossary.from_defaults(enrich_ingest=False)
    msg = "РП и АМ"
    assert g.enrich_text(msg) == msg
