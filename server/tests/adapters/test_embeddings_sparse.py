"""
ANCHOR: tests.adapters.test_embeddings_sparse
PURPOSE: Sparse embed — API failure / dense-only → local token-weight fallback.
Dependencies: HttpEmbeddingsClient + httpx.MockTransport
"""

from __future__ import annotations

import httpx
import pytest

from app.adapters.embeddings.http import (
    HttpEmbeddingsClient,
    local_token_weights,
    parse_sparse_embedding,
)


def test_local_token_weights_basic() -> None:
    w = local_token_weights("РП отвечает за планирование поставок")
    assert "планирование" in w or "отвечает" in w
    assert all(len(k) > 2 for k in w)


def test_parse_sparse_rejects_dense_list() -> None:
    assert parse_sparse_embedding([0.1, 0.2, 0.3]) is None


def test_parse_sparse_accepts_token_map_and_indices() -> None:
    assert parse_sparse_embedding({"отчетность": 1.0, "проект": 2.0}) == {
        "отчетность": 1.0,
        "проект": 2.0,
    }
    parsed = parse_sparse_embedding({"indices": [10, 20], "values": [0.5, 1.5]})
    assert parsed == {"10": 0.5, "20": 1.5}


@pytest.mark.asyncio
async def test_embed_sparse_falls_back_on_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "model not found"})

    transport = httpx.MockTransport(handler)
    client = HttpEmbeddingsClient(
        base_url="https://emb.test/v1",
        api_key="k",
        dense_model="dense",
        sparse_model="sparse",
    )

    # Patch AsyncClient construction inside _embed via monkeypatch of module httpx.
    import app.adapters.embeddings.http as emb_mod

    real_async = emb_mod.httpx.AsyncClient

    def _client(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs = dict(kwargs)
        kwargs["transport"] = transport
        kwargs.setdefault("base_url", "")
        return real_async(*args, **kwargs)

    emb_mod.httpx.AsyncClient = _client  # type: ignore[assignment]
    try:
        out = await client.embed_sparse(["планирование поставок менеджер"])
    finally:
        emb_mod.httpx.AsyncClient = real_async  # type: ignore[assignment]

    assert len(out) == 1
    assert out[0] == local_token_weights("планирование поставок менеджер")


@pytest.mark.asyncio
async def test_embed_sparse_falls_back_when_api_returns_dense() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 0, "embedding": [0.1, 0.2, 0.3, 0.4]},
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    client = HttpEmbeddingsClient(
        base_url="https://emb.test/v1",
        api_key=None,
        dense_model="dense",
        sparse_model="sparse-that-is-dense",
    )
    import app.adapters.embeddings.http as emb_mod

    real_async = emb_mod.httpx.AsyncClient

    def _client(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs = dict(kwargs)
        kwargs["transport"] = transport
        return real_async(*args, **kwargs)

    emb_mod.httpx.AsyncClient = _client  # type: ignore[assignment]
    try:
        text = "кто отвечает за планирование поставок"
        out = await client.embed_sparse([text])
    finally:
        emb_mod.httpx.AsyncClient = real_async  # type: ignore[assignment]

    assert out[0] == local_token_weights(text)
