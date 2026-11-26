"""
ANCHOR: tests.adapters.test_llm_reasoning_tokens
PURPOSE: LLM_REASONING_TOKENS is added to LLM_MAX_TOKENS in chat completions payload.
Dependencies: HttpLLMClient; httpx.MockTransport
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.adapters.llm.http import HttpLLMClient
from app.config.factories import _build_llm
from app.config.settings import Settings


@pytest.mark.asyncio
async def test_complete_sends_max_plus_reasoning(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.read().decode("utf-8"))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}}]},
        )

    transport = httpx.MockTransport(handler)
    real = httpx.AsyncClient

    def _client(*args, **kwargs):
        kwargs["transport"] = transport
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", _client)

    client = HttpLLMClient(
        base_url="https://llm.test.invalid/v1",
        api_key=None,
        model="m",
        max_tokens=1500,
        reasoning_tokens=1024,
    )
    assert client.request_max_tokens == 2524
    text = await client.complete(system="s", user="u")
    assert text == "ok"
    assert captured["body"]["max_tokens"] == 2524


def test_factory_wires_reasoning_into_client() -> None:
    settings = Settings(LLM_MAX_TOKENS=1500, LLM_REASONING_TOKENS=1024)
    client = _build_llm(settings)
    assert client.request_max_tokens == 2524
