"""
ANCHOR: tests.domain.test_allowed_topics
PURPOSE: Parse / resolve ALLOWED_TOPICS; refusal + mention helpers.
Dependencies: app.domain.allowed_topics
"""

from __future__ import annotations

from app.domain.allowed_topics import (
    CORE_ALLOWED_TOPIC,
    AllowedTopic,
    build_refusal_message,
    format_topics_for_prompt,
    includes_legal_topics,
    mentions_allowed_topic,
    parse_allowed_topics,
    resolve_allowed_topics,
    resolve_prompt_mode,
)


def test_parse_allowed_topics_labels_and_descriptions() -> None:
    raw = (
        "Конституция РФ=основной закон РФ;"
        "Трудовой кодекс РФ: трудовые отношения|"
        "Гражданский кодекс РФ"
    )
    got = parse_allowed_topics(raw)
    assert [t.label for t in got] == [
        "Конституция РФ",
        "Трудовой кодекс РФ",
        "Гражданский кодекс РФ",
    ]
    assert got[0].description == "основной закон РФ"
    assert got[1].description == "трудовые отношения"
    assert got[2].description == ""


def test_resolve_always_includes_core() -> None:
    topics = resolve_allowed_topics("Конституция РФ")
    assert topics[0] == CORE_ALLOWED_TOPIC
    assert topics[1].label == "Конституция РФ"


def test_mentions_allowed_topic_and_refusal_lists_extras() -> None:
    topics = resolve_allowed_topics(
        "Конституция РФ=основной закон;Трудовой кодекс РФ"
    )
    assert mentions_allowed_topic(
        "Что говорит Конституция о свободе слова?", topics
    )
    assert mentions_allowed_topic("Нормы трудового кодекса про отпуск", topics)
    assert not mentions_allowed_topic("Какая погода?", topics)

    refusal = build_refusal_message(topics)
    assert "Конституция РФ" in refusal
    assert "Трудовой кодекс РФ" in refusal
    assert "корпоративные регламенты" in refusal

    prompt = format_topics_for_prompt(topics)
    assert "Конституция РФ: основной закон" in prompt
    assert CORE_ALLOWED_TOPIC.label in prompt


def test_empty_parse() -> None:
    assert parse_allowed_topics(None) == []
    assert parse_allowed_topics("  ") == []
    assert resolve_allowed_topics(None) == [CORE_ALLOWED_TOPIC]


def test_prompt_mode_regs_only_vs_legal() -> None:
    assert resolve_prompt_mode(None) == "regs_only"
    assert resolve_prompt_mode(resolve_allowed_topics(None)) == "regs_only"
    assert not includes_legal_topics(resolve_allowed_topics("Брендбук=логотип"))

    legal = resolve_allowed_topics(
        "Конституция РФ=основной закон;Трудовой кодекс РФ"
    )
    assert includes_legal_topics(legal)
    assert resolve_prompt_mode(legal) == "regs_legal"
    assert includes_legal_topics(resolve_allowed_topics("ТК РФ=нормы труда"))
