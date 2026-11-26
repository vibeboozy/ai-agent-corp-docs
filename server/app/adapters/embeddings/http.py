"""
ANCHOR: app.adapters.embeddings.HttpEmbeddingsClient
PURPOSE: Real HttpEmbeddingsClient adapter skeleton — NotImplemented until live-adapter phase.
Dependencies: httpx; Settings
CRITICAL: Selected only when USE_STUBS=false and matching *_USE_STUB=false.
DO:
- Enforce *_TIMEOUT_S on clients
- Map failures to typed errors without leaking secrets
DONT:
- Call from application without DI factory
"""

from __future__ import annotations

from typing import Any

from app.adapters.embeddings.port import EmbeddingsClient


class HttpEmbeddingsClient:
    """Real provider skeleton."""

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    async def invoke(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("HttpEmbeddingsClient not implemented")


# Structural compatibility with EmbeddingsClient
_: EmbeddingsClient = HttpEmbeddingsClient()  # type: ignore[assignment]
