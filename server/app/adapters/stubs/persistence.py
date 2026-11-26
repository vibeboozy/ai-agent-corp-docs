"""
ANCHOR: app.adapters.stubs.persistence
PURPOSE: StubPersistence — in-memory store for unit tests (not durable).
Dependencies: app.adapters.persistence.port.Persistence
DO:
- Use for unit tests and default CI
DONT:
- Use as demo durability across restarts
"""

from __future__ import annotations

from typing import Any

from app.adapters.persistence.port import Persistence


class StubPersistence:
    """In-memory persistence skeleton."""

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    async def ping(self) -> bool:
        return True

    async def invoke(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("StubPersistence repository methods not implemented")


_: Persistence = StubPersistence()  # type: ignore[assignment]
