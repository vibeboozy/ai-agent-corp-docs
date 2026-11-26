"""
ANCHOR: tests.adapters.test_llm_classify
PURPOSE: classify_specificity strips <think> and ignores labels inside reasoning.
Dependencies: app.adapters.llm.http
"""

from __future__ import annotations

import pytest

from app.adapters.llm.http import HttpLLMClient, parse_specificity_label, strip_think_blocks


def test_strip_think_blocks() -> None:
    raw = "<think>maybe underspecified?</think>\nspecific"
    assert strip_think_blocks(raw) == "specific"


def test_parse_specificity_ignores_think_underspecified() -> None:
    # Root cause of API clarifying while direct answers looked "specific":
    # models emit <think>…underspecified…</think> then the real label.
    raw = (
        "<think>\nThe question could be underspecified without a department, "
        "but enough context exists.\n</think>\nspecific"
    )
    assert parse_specificity_label(raw) == "specific"


def test_parse_specificity_exact_token() -> None:
    assert parse_specificity_label("ambiguous") == "ambiguous"
    assert parse_specificity_label("Underspecified.") == "underspecified"


@pytest.mark.asyncio
async def test_http_classify_uses_strip_path(monkeypatch: pytest.MonkeyPatch) -> None:
    client = HttpLLMClient(
        base_url="https://example.invalid/v1",
        api_key=None,
        model="test",
    )

    async def fake_complete(*, system: str, user: str, temperature: float | None = None) -> str:
        _ = (system, user, temperature)
        return "<think>underspecified reasoning</think>\nspecific"

    monkeypatch.setattr(client, "complete", fake_complete)
    assert await client.classify_specificity("Кто подписывает договоры на закупку?") == "specific"
