"""
ANCHOR: app.adapters.docling.port
PURPOSE: DoclingClient Protocol/ABC — no Stub prefix (CS-STUB-01).
Dependencies: typing.Protocol
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class DoclingClient(Protocol):
    async def invoke(self, *args: Any, **kwargs: Any) -> Any:
        """Port method placeholder — refine signatures in implementation phases."""
        ...
