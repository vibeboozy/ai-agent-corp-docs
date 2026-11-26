"""
ANCHOR: tests.adapters.test_embeddings_batch
PURPOSE: EMBEDDINGS_BATCH_SIZE splits /embeddings requests (httpx mock).
Dependencies: HttpEmbeddingsClient
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.adapters.embeddings.http import HttpEmbeddingsClient


@pytest.mark.asyncio
async def test_embed_dense_batches_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.read().decode("utf-8"))
        batch = body["input"]
        calls.append(batch)
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": i, "embedding": [float(i), 0.0]} for i in range(len(batch))
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    real = httpx.AsyncClient

    def _client(*args, **kwargs):
        kwargs["transport"] = transport
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", _client)

    client = HttpEmbeddingsClient(
        base_url="https://emb.test.invalid/v1",
        api_key=None,
        dense_model="dense",
        sparse_model="sparse",
        batch_size=2,
    )
    vectors = await client.embed_dense(["a", "b", "c", "d", "e"])
    assert len(vectors) == 5
    assert calls == [["a", "b"], ["c", "d"], ["e"]]
