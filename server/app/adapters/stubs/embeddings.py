"""
ANCHOR: app.adapters.stubs.embeddings
PURPOSE: StubEmbeddingsClient — deterministic zero/hash vectors (offline).
Dependencies: app.adapters.embeddings.port.EmbeddingsClient
DO:
- Keep offline and side-effect free
DONT:
- Perform real network I/O
"""

from __future__ import annotations

import hashlib

from app.adapters.embeddings.port import EmbeddingsClient


class StubEmbeddingsClient:
    """Deterministic pseudo-embeddings from text hashes."""

    def __init__(self, dim: int = 32) -> None:
        self._dim = dim

    async def embed_dense(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            vals = [((digest[i % len(digest)] / 255.0) * 2 - 1) for i in range(self._dim)]
            out.append(vals)
        return out

    async def embed_sparse(self, texts: list[str]) -> list[dict[str, float]]:
        result: list[dict[str, float]] = []
        for text in texts:
            weights: dict[str, float] = {}
            for token in text.lower().split():
                if len(token) > 2:
                    weights[token] = weights.get(token, 0.0) + 1.0
            result.append(weights)
        return result


_: EmbeddingsClient = StubEmbeddingsClient()  # type: ignore[assignment]
