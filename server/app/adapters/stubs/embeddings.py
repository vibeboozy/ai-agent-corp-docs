"""
ANCHOR: app.adapters.stubs.embeddings
PURPOSE: StubEmbeddingsClient — deterministic fixture responses (skeleton).
Dependencies: app.adapters.embeddings.port.EmbeddingsClient
DO:
- Keep offline and side-effect free
DONT:
- Perform real network I/O
"""

from __future__ import annotations

from typing import Any

from app.adapters.embeddings.port import EmbeddingsClient


class StubEmbeddingsClient:
    """Stub provider skeleton."""

    async def invoke(self, *args: Any, **kwargs: Any) -> Any:
        # TODO: return deterministic fixtures for demo/tests
        raise NotImplementedError("StubEmbeddingsClient fixture responses not implemented")


_: EmbeddingsClient = StubEmbeddingsClient()  # type: ignore[assignment]
