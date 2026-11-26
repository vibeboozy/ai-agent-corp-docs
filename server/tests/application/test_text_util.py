"""
ANCHOR: tests.application.test_text_util
PURPOSE: Sentence-safe truncate / quote boundary / lexical overlap.
Dependencies: app.application.text_util
"""

from __future__ import annotations

from app.application.text_util import (
    complete_sentences,
    lexical_overlap,
    quote_at_boundary,
    truncate_at_sentence,
)


def test_truncate_at_sentence_avoids_mid_thought() -> None:
    text = (
        "Согласно регламенту: за планирование поставок отвечает Менеджер по поставке. "
        "При его отсутствии — АМ. Далее идёт длинный хвост который не нужен в summary "
        + ("слово " * 80)
    )
    out = truncate_at_sentence(text, 120)
    assert len(out) <= 120
    assert not out.endswith("котор")  # not mid-word of хвост fragment ideally
    assert out.endswith(".") or out.endswith("…")


def test_quote_at_boundary_strips_leading_remnant() -> None:
    raw = (
        "проекта. Исключением является прямое письменное указание. "
        "**17.3.** Исполнители выполняют работы."
    )
    q = quote_at_boundary(raw, 200)
    assert not q.lower().startswith("проекта.")
    assert "17.3" in q or "Исключением" in q


def test_complete_sentences_drops_trailing_fragment() -> None:
    text = "Первое предложение полностью. Второе тоже готово. Обрезанный хвост без точк"
    out = complete_sentences(text, max_chars=200)
    assert out.endswith(".")
    assert "хвост" not in out


def test_lexical_overlap_prefers_matching_section() -> None:
    q = "планирование поставок"
    good = "7.2. Планирование поставок. За планирование поставок отвечает Менеджер."
    bad = "17.3. Исполнители команды проекта выполняют работы по план-графику."
    assert lexical_overlap(q, good) > lexical_overlap(q, bad)
