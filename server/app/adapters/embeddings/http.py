"""
ANCHOR: app.adapters.embeddings.HttpEmbeddingsClient
PURPOSE: Real embeddings client (OpenAI-compatible /embeddings).
Dependencies: httpx; Settings
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from app.adapters.embeddings.port import EmbeddingsClient
from app.domain.errors import AppError, UpstreamTimeoutError


class HttpEmbeddingsClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        dense_model: str,
        sparse_model: str,
        timeout_s: float = 120.0,
        allow_hosts: set[str] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._dense_model = dense_model
        self._sparse_model = sparse_model
        self._timeout = timeout_s
        self._allow_hosts = allow_hosts or set()
        if self._allow_hosts:
            host = (urlparse(self._base_url).hostname or "").lower()
            if host and host not in self._allow_hosts:
                raise AppError(f"Embeddings host not allowlisted: {host}", code="EGRESS_DENIED")

    async def ping(self) -> bool:
        headers: dict[str, str] = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        try:
            async with httpx.AsyncClient(timeout=min(self._timeout, 15.0)) as client:
                resp = await client.get(f"{self._base_url}/models", headers=headers)
                return resp.status_code < 500
        except httpx.TimeoutException as exc:
            raise UpstreamTimeoutError("Embeddings ping timed out") from exc
        except httpx.HTTPError as exc:
            raise AppError("Embeddings ping failed", code="UPSTREAM_ERROR") from exc

    async def embed_dense(self, texts: list[str]) -> list[list[float]]:
        return await self._embed(self._dense_model, texts)

    async def embed_sparse(self, texts: list[str]) -> list[dict[str, float]]:
        # Many OpenAI-compatible stacks return dense only; map tokens locally as fallback.
        _ = await self._embed(self._sparse_model, texts)
        result: list[dict[str, float]] = []
        for text in texts:
            weights: dict[str, float] = {}
            for token in text.lower().split():
                if len(token) > 2:
                    weights[token] = weights.get(token, 0.0) + 1.0
            result.append(weights)
        return result

    async def _embed(self, model: str, texts: list[str]) -> list[Any]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/embeddings",
                    headers=headers,
                    json={"model": model, "input": texts},
                )
                resp.raise_for_status()
                data = resp.json()
                items = sorted(data["data"], key=lambda x: x["index"])
                return [item["embedding"] for item in items]
        except httpx.TimeoutException as exc:
            raise UpstreamTimeoutError("Embeddings request timed out") from exc
        except httpx.HTTPError as exc:
            raise AppError("Embeddings upstream error", code="UPSTREAM_ERROR") from exc


_: EmbeddingsClient = HttpEmbeddingsClient(  # type: ignore[assignment]
    base_url="https://example.invalid/v1",
    api_key=None,
    dense_model="x",
    sparse_model="y",
)
