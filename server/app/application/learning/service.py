"""
ANCHOR: app.application.learning.service
PURPOSE: Officer canonical answer → KB update (ANC-LEARN-01).
Dependencies: persistence, ingest, appeals
CRITICAL: Missing KB + officer reply MUST update KB (ANC-LEARN-01).
DO:
- Log all learning events
DONT:
- Silent message append without learning side-effects
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.adapters.persistence.port import Persistence
from app.application.ingest.service import IngestService
from app.domain.enums import AppealStatus, EscalationStatus, MessageKind, MessageRole
from app.domain.errors import ConflictError, NotFoundError
from app.domain.models import Appeal, Message


@dataclass
class LearningResult:
    appeal: Appeal
    message: Message
    accepted: bool
    ingest_job_id: str | None
    escalation_id: UUID | None


class LearningService:
    def __init__(self, *, persistence: Persistence, ingest: IngestService) -> None:
        self._persistence = persistence
        self._ingest = ingest

    async def officer_reply(
        self,
        *,
        appeal_id: UUID,
        content: str,
        source_document_hint: str | None = None,
    ) -> LearningResult:
        appeal = await self._persistence.get_appeal(appeal_id)
        if appeal is None:
            raise NotFoundError(f"Appeal {appeal_id} not found")
        if appeal.status == AppealStatus.CLOSED:
            raise ConflictError("Appeal is closed")

        messages = await self._persistence.list_messages(appeal_id, limit=200)
        keywords = _keywords_from_history(messages, content)

        msg = await self._persistence.add_message(
            appeal_id=appeal_id,
            role=MessageRole.OFFICER,
            message_kind=MessageKind.CANONICAL_ANSWER,
            content=content,
            citations=[],
        )

        ingest_meta = await self._ingest.ingest_text(
            text=content,
            document_title=source_document_hint or "Канонический ответ офицера качества",
            keywords=keywords,
            metadata={
                "appeal_id": str(appeal_id),
                "escalation_id": str(appeal.escalation_id) if appeal.escalation_id else None,
                "source_document_hint": source_document_hint,
            },
        )

        if appeal.escalation_id is not None:
            await self._persistence.update_escalation(
                appeal.escalation_id,
                status=EscalationStatus.ANSWERED,
                officer_reply_at=msg.created_at,
            )

        updated = await self._persistence.update_appeal(
            appeal_id,
            status=AppealStatus.RESOLVED_BY_OFFICER,
            summary=(content[:240] if content else None),
        )
        await self._persistence.increment_learning_updates()
        await self._persistence.add_audit_event(
            appeal_id=appeal_id,
            event_type="learning_accepted",
            payload={
                "ingest_job_id": ingest_meta["ingest_job_id"],
                "message_id": str(msg.id),
            },
        )
        return LearningResult(
            appeal=updated,
            message=msg,
            accepted=True,
            ingest_job_id=ingest_meta["ingest_job_id"],
            escalation_id=appeal.escalation_id,
        )


def _keywords_from_history(messages: list[Message], content: str) -> list[str]:
    blob = " ".join(m.content for m in messages if m.role.value == "user") + " " + content
    tokens = [t.strip(".,!?«»\"'").lower() for t in blob.split()]
    # Keep informative tokens for stub keyword search.
    stop = {"это", "про", "для", "или", "как", "что", "кто", "при", "без", "the", "and"}
    out: list[str] = []
    for t in tokens:
        if len(t) >= 4 and t not in stop and t not in out:
            out.append(t)
        if len(out) >= 16:
            break
    # Always include stems useful for re-ask demos
    for stem in ("закупк", "подрядчик", "отпуск", "договор", "подпис", "логотип", "брендбук"):
        if stem in blob.lower() and stem not in out:
            out.append(stem)
    return out
