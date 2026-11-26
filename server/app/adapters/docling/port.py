"""
ANCHOR: app.adapters.docling.port
PURPOSE: DoclingClient Protocol/ABC — no Stub prefix (CS-STUB-01).
Dependencies: typing.Protocol
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class DoclingClient(Protocol):
    async def convert(self, *, source_path: str | None = None, text: str | None = None) -> dict[str, Any]:
        """Convert document or raw text into structured chunks."""
        ...
