"""
ANCHOR: app.adapters.stubs.docling
PURPOSE: StubDoclingClient — splits text into pseudo-chunks (offline).
Dependencies: app.adapters.docling.port.DoclingClient
DO:
- Keep offline and side-effect free
DONT:
- Perform real network I/O
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.adapters.docling.port import DoclingClient


class StubDoclingClient:
    """Simple paragraph splitter standing in for Docling HTTP."""

    async def convert(self, *, source_path: str | None = None, text: str | None = None) -> dict[str, Any]:
        body = text or (f"[stub convert of {source_path}]" if source_path else "")
        paragraphs = [p.strip() for p in body.split("\n") if p.strip()] or [body]
        chunks = [
            {
                "chunk_id": f"docling-{uuid4().hex[:8]}",
                "text": p,
                "token_count": max(1, len(p.split())),
            }
            for p in paragraphs
        ]
        return {"source_path": source_path, "chunks": chunks}


_: DoclingClient = StubDoclingClient()  # type: ignore[assignment]
