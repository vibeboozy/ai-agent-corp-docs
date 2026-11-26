"""
ANCHOR: app.adapters.escalation.port
PURPOSE: EscalationNotifier Protocol/ABC — no Stub prefix (CS-STUB-01).
Dependencies: typing.Protocol
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable
from uuid import UUID


@runtime_checkable
class EscalationNotifier(Protocol):
    async def notify(
        self,
        *,
        appeal_id: UUID,
        escalation_id: UUID,
        reason: str,
        summary: str,
    ) -> dict[str, Any]:
        """Notify quality service; return delivery metadata."""
        ...
