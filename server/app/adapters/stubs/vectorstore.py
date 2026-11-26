"""
ANCHOR: app.adapters.stubs.vectorstore
PURPOSE: StubVectorStore — deterministic fixture responses (skeleton).
Dependencies: app.adapters.vectorstore.port.VectorStore
DO:
- Keep offline and side-effect free
DONT:
- Perform real network I/O
"""

from __future__ import annotations

from typing import Any

from app.adapters.vectorstore.port import VectorStore


class StubVectorStore:
    """Stub provider skeleton."""

    async def invoke(self, *args: Any, **kwargs: Any) -> Any:
        # TODO: return deterministic fixtures for demo/tests
        raise NotImplementedError("StubVectorStore fixture responses not implemented")


_: VectorStore = StubVectorStore()  # type: ignore[assignment]
