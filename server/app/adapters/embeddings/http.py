"""
ANCHOR: app.adapters.embeddings.HttpEmbeddingsClient
PURPOSE: Real embeddings client (OpenAI-compatible /embeddings).
Dependencies: httpx; Settings
DO:
- Batch dense embeds; sparse tries API then local token-weight fallback
DONT:
- Fail ingest/search when sparse model returns dense-only or 4xx
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from app.adapters.embeddings.port import EmbeddingsClient
from app.domain.errors import AppError, UpstreamTimeoutError

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[^\W_]+(?:-[^\W_]+)*", re.UNICODE)


def local_token_weights(text: str) -> dict[str, float]:
    """Local sparse fallback: token → term frequency (len > 2)."""
    weights: dict[str, float] = {}
    for token in _TOKEN_RE.findall((text or "").lower()):
        if len(token) > 2:
            weights[token] = weights.get(token, 0.0) + 1.0
    return weights


def parse_sparse_embedding(item: Any) -> dict[str, float] | None:
    """
    Normalize an embeddings API item into token→weight (or index→weight) map.

    Returns None when the payload looks dense-only / empty so callers fall back.
    Accepts:
    - dict[str, float] token weights
    - {"indices": [...], "values": [...]} (stringified indices as keys)
    - {"embedding": {...}} / nested sparse object
    """
    if item is None:
        return None
    if isinstance(item, list):
        # Dense float vector — not usable as sparse token weights.
        return None
    if not isinstance(item, dict):
        return None

    # Nested OpenAI-style or vendor wrappers.
    if "embedding" in item and item["embedding"] is not item:
        nested = parse_sparse_embedding(item["embedding"])
        if nested is not None:
            return nested
    for key in ("sparse", "sparse_embedding", "lexical_weights"):
        if key in item and isinstance(item[key], dict):
            nested = parse_sparse_embedding(item[key])
            if nested is not None:
                return nested

    if "indices" in item and "values" in item:
        indices = list(item.get("indices") or [])
        values = list(item.get("values") or [])
        if not indices or len(indices) != len(values):
            return None
        out: dict[str, float] = {}
        for idx, val in zip(indices, values, strict=False):
            out[str(idx)] = float(val)
        return out or None

    # Flat token→weight map (skip non-numeric values / meta keys).
    meta = {"indices", "values", "object", "index", "model", "embedding"}
    weights: dict[str, float] = {}
    for key, val in item.items():
        if key in meta:
            continue
        try:
            weights[str(key)] = float(val)
        except (TypeError, ValueError):
            return None
    return weights or None


class HttpEmbeddingsClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        dense_model: str,
        sparse_model: str,
        timeout_s: float = 120.0,
        batch_size: int = 32,
        allow_hosts: set[str] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._dense_model = dense_model
        self._sparse_model = sparse_model
        self._timeout = timeout_s
        self._batch_size = max(1, int(batch_size))
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
        raw = await self._embed(self._dense_model, texts)
        out: list[list[float]] = []
        for item in raw:
            if isinstance(item, list):
                out.append([float(x) for x in item])
            elif isinstance(item, dict) and isinstance(item.get("embedding"), list):
                out.append([float(x) for x in item["embedding"]])
            else:
                raise AppError("Dense embedding response malformed", code="UPSTREAM_ERROR")
        return out

    async def embed_sparse(self, texts: list[str]) -> list[dict[str, float]]:
        """
        Prefer sparse API when it returns usable weights; otherwise local TF map.

        OpenAI-compatible stacks often only expose dense models — never fail the
        call path for that: catch upstream errors and dense-only payloads.
        """
        fallback = [local_token_weights(t) for t in texts]
        if not texts:
            return []
        try:
            raw = await self._embed(self._sparse_model, texts)
        except Exception as exc:  # noqa: BLE001 — intentional soft-fail to local sparse
            logger.info("sparse embed API unavailable (%s); using local token weights", exc)
            return fallback

        result: list[dict[str, float]] = []
        for idx, item in enumerate(raw):
            parsed = parse_sparse_embedding(item)
            if parsed:
                result.append(parsed)
            else:
                result.append(fallback[idx] if idx < len(fallback) else {})
        # Pad if upstream returned fewer rows than inputs.
        while len(result) < len(texts):
            result.append(fallback[len(result)])
        return result

    async def _embed(self, model: str, texts: list[str]) -> list[Any]:
        if not texts:
            return []
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        out: list[Any] = []
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                for start in range(0, len(texts), self._batch_size):
                    batch = texts[start : start + self._batch_size]
                    resp = await client.post(
                        f"{self._base_url}/embeddings",
                        headers=headers,
                        json={"model": model, "input": batch},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    items = sorted(data["data"], key=lambda x: x["index"])
                    # Keep full item so sparse parsers can see nested shapes;
                    # dense path reads embedding list.
                    out.extend(item.get("embedding", item) for item in items)
            return out
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
