"""
ANCHOR: app.adapters.llm.port
PURPOSE: LLMClient Protocol/ABC — no Stub prefix (CS-STUB-01).
Dependencies: typing.Protocol
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    async def complete(
        self,
        *,
        system: str,
        user: str,
        temperature: float | None = None,
    ) -> str:
        """Return assistant text completion."""
        ...

    async def classify_specificity(self, user_message: str, history: list[str] | None = None) -> str:
        """
        Return one of: underspecified | specific | ambiguous.
        Used by assess_specificity node (stub or live).
        """
        ...
