"""
ANCHOR: tests.application.test_text_util
PURPOSE: Sentence-safe truncate / quote boundary / lexical overlap.
Dependencies: app.application.text_util
"""

from __future__ import annotations

from app.application.text_util import (
    complete_sentences,
    cut_before_next_clause,
    lexical_overlap,
    quote_at_boundary,
    strip_think_blocks,
    truncate_at_sentence,
)


def test_strip_think_blocks_closed() -> None:
    raw = (
        "<think>\nReasoning about risks in English.\n</think>\n"
        "За планирование рисков отвечает РП."
    )
    assert strip_think_blocks(raw) == "За планирование рисков отвечает РП."


def test_strip_think_blocks_no_think() -> None:
    clean = "За подтверждение сроков отвечает АМ."
    assert strip_think_blocks(clean) == clean


def test_strip_think_blocks_unclosed() -> None:
    raw = "<think>still reasoning without a close tag\nи хвост"
    assert strip_think_blocks(raw) == ""


def test_strip_think_blocks_think_then_answer() -> None:
    raw = (
        "<thinking>step one</thinking>\n"
        "<think>step two</think>\n\n"
        "Ответ: сроки подтверждает менеджер проекта."
    )
    assert strip_think_blocks(raw) == "Ответ: сроки подтверждает менеджер проекта."


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


def test_cut_before_next_clause_drops_trailing_bold_number() -> None:
    """Regression: summary must not end with bleed of next clause (``**10.``)."""
    raw = (
        "**9.5.** Договоры на закупку подписывают уполномоченные представители "
        "юридических лиц Компании. **10."
    )
    out = cut_before_next_clause(raw)
    assert out.endswith("Компании.")
    assert "**10" not in out
    assert "9.5" in out


def test_complete_sentences_stops_before_next_clause_heading() -> None:
    raw = (
        "Согласно регламенту «Закупки»: **9.5.** Договоры на закупку подписывают "
        "уполномоченные представители юридических лиц Компании. **10. Порядок "
        "согласования заявок."
    )
    out = complete_sentences(raw, max_chars=900)
    assert "юридических лиц Компании." in out
    assert "**10" not in out
    assert "Порядок согласования" not in out
    assert out.rstrip().endswith("Компании.")


def test_truncate_at_sentence_summary_no_next_clause_bleed() -> None:
    """Appeal summary path: truncate_at_sentence must strip ``**10.`` bleed."""
    answer = (
        "Согласно регламенту «Закупки»: **9.5.** Договоры на закупку подписывают "
        "уполномоченные представители юридических лиц Компании. **10."
    )
    summary = truncate_at_sentence(answer, 480)
    assert "**10" not in summary
    assert summary.rstrip().endswith("Компании.")


def test_lexical_overlap_prefers_matching_section() -> None:
    q = "планирование поставок"
    good = "7.2. Планирование поставок. За планирование поставок отвечает Менеджер."
    bad = "17.3. Исполнители команды проекта выполняют работы по план-графику."
    assert lexical_overlap(q, good) > lexical_overlap(q, bad)
