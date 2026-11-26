"""
ANCHOR: tests.adapters.test_llm_classify
PURPOSE: classify_specificity strips <think> and ignores labels inside reasoning.
Dependencies: app.adapters.llm.http; httpx.MockTransport (no live URLs)
"""

from __future__ import annotations

import httpx
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


@pytest.mark.asyncio
async def test_classify_via_httpx_mock_transport_strips_think(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end classify through complete() with mocked OpenAI chat HTTP (no network)."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["raw"] = request.read().decode("utf-8")
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                "<think>This looks underspecified without dept.</think>\n"
                                "specific"
                            )
                        }
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    def _client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", _client)

    client = HttpLLMClient(
        base_url="https://llm.test.invalid/v1",
        api_key="k",
        model="test-model",
    )
    label = await client.classify_specificity("Кто подписывает договоры на закупку?")
    assert label == "specific"
    assert captured["url"].endswith("/chat/completions")
    assert "Classifier" in captured["raw"] or "Question" in captured["raw"]
