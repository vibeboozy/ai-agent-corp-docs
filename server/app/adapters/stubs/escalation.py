"""
ANCHOR: app.adapters.stubs.escalation
PURPOSE: StubEscalationNotifier — records notifications in-memory (no email).
Dependencies: app.adapters.escalation.port.EscalationNotifier
DO:
- Keep offline and side-effect free
DONT:
- Perform real network I/O
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.adapters.escalation.port import EscalationNotifier


class StubEscalationNotifier:
    """Records notify calls for assertions in tests."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def notify(
        self,
        *,
        appeal_id: UUID,
        escalation_id: UUID,
        reason: str,
        summary: str,
    ) -> dict[str, Any]:
        payload = {
            "appeal_id": str(appeal_id),
            "escalation_id": str(escalation_id),
            "reason": reason,
            "summary": summary,
            "channel": "stub",
            "delivered": True,
        }
        self.sent.append(payload)
        return payload


_: EscalationNotifier = StubEscalationNotifier()  # type: ignore[assignment]
