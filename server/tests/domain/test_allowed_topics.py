"""
ANCHOR: tests.domain.test_allowed_topics
PURPOSE: Domain mode topics; refusal + mention helpers.
Dependencies: app.domain.allowed_topics
"""

from __future__ import annotations

from app.domain.allowed_topics import (
    CORE_ALLOWED_TOPIC,
    LEGAL_BAKED_TOPICS,
    build_refusal_message,
    format_topics_for_prompt,
    is_legal_mode,
    mentions_allowed_topic,
    normalize_domain_mode,
    resolve_prompt_mode,
    topics_for_mode,
)


def test_normalize_domain_mode() -> None:
    assert normalize_domain_mode(None) == "regs_only"
    assert normalize_domain_mode("") == "regs_only"
    assert normalize_domain_mode("regs_only") == "regs_only"
    assert normalize_domain_mode("regs_legal") == "regs_legal"
    assert normalize_domain_mode("regs+legal") == "regs_legal"
    assert normalize_domain_mode("LEGAL") == "regs_legal"
    assert normalize_domain_mode("garbage") == "regs_only"


def test_topics_for_regs_only() -> None:
    topics = topics_for_mode("regs_only")
    assert topics == [CORE_ALLOWED_TOPIC]
    assert not is_legal_mode("regs_only")
    assert resolve_prompt_mode("regs_only") == "regs_only"


def test_topics_for_regs_legal_bakes_constitution_and_tk() -> None:
    topics = topics_for_mode("regs_legal")
    assert topics[0] == CORE_ALLOWED_TOPIC
    assert [t.label for t in topics[1:]] == [t.label for t in LEGAL_BAKED_TOPICS]
    assert "Конституция РФ" in {t.label for t in topics}
    assert "Трудовой кодекс РФ" in {t.label for t in topics}
    assert is_legal_mode("regs_legal")
    assert resolve_prompt_mode("regs_legal") == "regs_legal"


def test_mentions_and_refusal_for_legal_mode() -> None:
    topics = topics_for_mode("regs_legal")
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
    assert "Конституция РФ: основной закон РФ" in prompt
    assert CORE_ALLOWED_TOPIC.label in prompt


def test_regs_only_refusal_preserves_historical_wording() -> None:
    refusal = build_refusal_message(topics_for_mode("regs_only"))
    assert "корпоративным регламентам и процессам" in refusal
    assert "Конституция" not in refusal
