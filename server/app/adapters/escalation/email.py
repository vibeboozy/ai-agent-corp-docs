"""
ANCHOR: app.adapters.escalation.email
PURPOSE: EmailEscalationNotifier — SMTP/webhook placeholder for quality alerts.
Dependencies: logging; Settings QUALITY_SERVICE_EMAIL
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.adapters.escalation.port import EscalationNotifier

logger = logging.getLogger(__name__)


class EmailEscalationNotifier:
    """Logs intended email payload; real SMTP can be wired later without API changes."""

    def __init__(self, *, to_email: str, subject_prefix: str = "[RAG-Escalation]") -> None:
        self._to = to_email
        self._prefix = subject_prefix

    async def notify(
        self,
        *,
        appeal_id: UUID,
        escalation_id: UUID,
        reason: str,
        summary: str,
    ) -> dict[str, Any]:
        subject = f"{self._prefix} appeal={appeal_id}"
        logger.info(
            "escalation_email_queued",
            extra={
                "to": self._to,
                "subject": subject,
                "appeal_id": str(appeal_id),
                "escalation_id": str(escalation_id),
                "reason": reason,
            },
        )
        return {
            "delivered": False,
            "queued": True,
            "to": self._to,
            "subject": subject,
            "summary": summary,
        }


_: EscalationNotifier = EmailEscalationNotifier(to_email="quality@example.invalid")  # type: ignore[assignment]
