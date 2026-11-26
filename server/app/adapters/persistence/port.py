"""
ANCHOR: app.adapters.persistence.port
PURPOSE: Persistence / repository Protocol.
Dependencies: domain models
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Persistence(Protocol):
    async def ping(self) -> bool:
        """Health check against the store."""
        ...

    async def invoke(self, *args: Any, **kwargs: Any) -> Any:
        """Catch-all placeholder until repository methods are defined."""
        ...
