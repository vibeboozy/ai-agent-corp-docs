"""
ANCHOR: app.adapters.stubs.docling
PURPOSE: StubDoclingClient — deterministic fixture responses (skeleton).
Dependencies: app.adapters.docling.port.DoclingClient
DO:
- Keep offline and side-effect free
DONT:
- Perform real network I/O
"""

from __future__ import annotations

from typing import Any

from app.adapters.docling.port import DoclingClient


class StubDoclingClient:
    """Stub provider skeleton."""

    async def invoke(self, *args: Any, **kwargs: Any) -> Any:
        # TODO: return deterministic fixtures for demo/tests
        raise NotImplementedError("StubDoclingClient fixture responses not implemented")


_: DoclingClient = StubDoclingClient()  # type: ignore[assignment]
