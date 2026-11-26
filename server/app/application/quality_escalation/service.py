"""
ANCHOR: app.application.quality_escalation.service
PURPOSE: Create escalation ticket + notify quality service (ANC-ESC-01).
Dependencies: escalation adapter, persistence, appeals
CRITICAL: Unsupported after clarify → escalate, do not invent (ANC-ESC-01).
DO:
- Treat escalation as successful business path
DONT:
- Return HTTP 500 for grounding failure alone
"""

from __future__ import annotations

from uuid import UUID

from app.adapters.escalation.port import EscalationNotifier
from app.adapters.persistence.port import Persistence
from app.domain.enums import AppealStatus, EscalationStatus
from app.domain.models import Escalation


class QualityEscalationService:
    def __init__(
        self,
        *,
        persistence: Persistence,
        notifier: EscalationNotifier,
        quality_email: str,
        enabled: bool = True,
    ) -> None:
        self._persistence = persistence
        self._notifier = notifier
        self._quality_email = quality_email
        self._enabled = enabled

    @property
    def quality_email(self) -> str:
        return self._quality_email

    def user_notice(self, reason: str) -> str:
        return (
            "К сожалению, в базе регламентов нет достаточных данных для ответа. "
            f"Обращение передано в службу качества ({self._quality_email}). "
            f"Причина: {reason}."
        )

    async def escalate(
        self,
        *,
        appeal_id: UUID,
        reason: str,
        summary: str,
    ) -> tuple[Escalation, str]:
        if not self._enabled:
            notice = (
                "Эскалация отключена конфигурацией; ответ не сформирован "
                f"(причина: {reason})."
            )
            return (
                Escalation(
                    id=appeal_id,
                    appeal_id=appeal_id,
                    reason=reason,
                    status=EscalationStatus.PENDING,
                ),
                notice,
            )

        esc = await self._persistence.create_escalation(
            appeal_id=appeal_id,
            reason=reason,
            channel="email",
        )
        await self._notifier.notify(
            appeal_id=appeal_id,
            escalation_id=esc.id,
            reason=reason,
            summary=summary,
        )
        await self._persistence.update_appeal(
            appeal_id,
            status=AppealStatus.ESCALATED,
            escalation_id=esc.id,
            summary=summary[:500],
        )
        return esc, self.user_notice(reason)
