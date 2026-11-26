"""
ANCHOR: app.application.dialogue.service
PURPOSE: Run one dialogue turn via LangGraph; persist outcome messages.
Dependencies: langgraph_runtime, retrieval, grounding, quality_escalation, llm port, persistence
CRITICAL: Clarify or escalate — never invent (ANC-CLARIFY-01, ANC-ESC-01, ANC-LG-01).
DO:
- Drive behavior via StateGraph edges
- Cap clarify turns via DIALOGUE_MAX_CLARIFY_TURNS
DONT:
- Use LangChain RetrievalQA as primary RAG
- Bypass grounding node
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.adapters.persistence.port import Persistence
from app.application.dialogue.audit import build_dialogue_turn_audit
from app.application.dialogue.graph import build_dialogue_graph
from app.application.dialogue.nodes import DialogueDeps
from app.application.dialogue.state import DialogueState
from app.application.quality_escalation.service import QualityEscalationService
from app.application.text_util import strip_think_blocks, truncate_at_sentence
from app.domain.enums import AppealStatus, MessageKind, MessageRole
from app.domain.errors import ConflictError, NotFoundError
from app.domain.models import Appeal, Message


@dataclass
class DialogueTurnResult:
    appeal: Appeal
    messages: list[Message]
    outcome: str
    node_trace: list[str]


class DialogueService:
    def __init__(
        self,
        *,
        persistence: Persistence,
        deps: DialogueDeps,
        escalation: QualityEscalationService,
        max_clarify_turns: int = 3,
    ) -> None:
        self._persistence = persistence
        self._deps = deps
        self._escalation = escalation
        self._max_clarify_turns = max_clarify_turns
        self._graph = build_dialogue_graph(deps)

    async def run_turn(
        self,
        *,
        appeal_id: UUID,
        content: str,
        role: MessageRole = MessageRole.USER,
    ) -> DialogueTurnResult:
        appeal = await self._persistence.get_appeal(appeal_id)
        if appeal is None:
            raise NotFoundError(f"Appeal {appeal_id} not found")
        if appeal.status == AppealStatus.CLOSED:
            raise ConflictError("Appeal is closed")
        if role != MessageRole.USER:
            raise ConflictError("Only user role is accepted on message endpoint", code="VALIDATION_ERROR")

        user_msg = await self._persistence.add_message(
            appeal_id=appeal_id,
            role=MessageRole.USER,
            message_kind=MessageKind.QUESTION,
            content=content,
        )

        history_msgs = await self._persistence.list_messages(appeal_id, limit=200)
        history = [m.content for m in history_msgs if m.role == MessageRole.USER and m.id != user_msg.id]
        clarify_turns = sum(
            1 for m in history_msgs if m.message_kind == MessageKind.CLARIFICATION
        )

        initial: DialogueState = {
            "appeal_id": str(appeal_id),
            "user_message": content,
            "history": history,
            "clarify_turns": clarify_turns,
            "max_clarify_turns": self._max_clarify_turns,
            "node_trace": [],
            "latency_ms": {},
        }
        turn_started = time.perf_counter()
        final: dict[str, Any] = await self._graph.ainvoke(initial)
        outcome = str(final.get("outcome") or "escalate")
        node_trace = list(final.get("node_trace") or [])
        citations = list(final.get("citations") or [])

        new_messages: list[Message] = [user_msg]

        if outcome == "refuse":
            refusal = strip_think_blocks(
                str(
                    final.get("draft_answer")
                    or final.get("clarification_text")
                    or "Этот вопрос не поддерживается."
                )
            )
            assistant = await self._persistence.add_message(
                appeal_id=appeal_id,
                role=MessageRole.ASSISTANT,
                message_kind=MessageKind.REFUSAL,
                content=refusal,
            )
            appeal = await self._persistence.update_appeal(
                appeal_id,
                status=AppealStatus.ANSWERED,
                summary=truncate_at_sentence(refusal, 480),
            )
            new_messages.append(assistant)
        elif outcome == "clarify":
            clarify_text = strip_think_blocks(
                str(final.get("clarification_text") or "Уточните вопрос, пожалуйста.")
            )
            assistant = await self._persistence.add_message(
                appeal_id=appeal_id,
                role=MessageRole.ASSISTANT,
                message_kind=MessageKind.CLARIFICATION,
                content=clarify_text,
            )
            appeal = await self._persistence.update_appeal(
                appeal_id, status=AppealStatus.CLARIFYING
            )
            new_messages.append(assistant)
        elif outcome == "answer":
            # First-generate path: never persist CoT that leaked into draft_answer.
            answer_text = strip_think_blocks(str(final.get("draft_answer") or ""))
            assistant = await self._persistence.add_message(
                appeal_id=appeal_id,
                role=MessageRole.ASSISTANT,
                message_kind=MessageKind.ANSWER,
                content=answer_text,
                citations=citations,
            )
            appeal = await self._persistence.update_appeal(
                appeal_id,
                status=AppealStatus.ANSWERED,
                summary=truncate_at_sentence(answer_text, 480),
            )
            new_messages.append(assistant)
        else:
            reason = str(final.get("escalation_reason") or "ungrounded")
            _esc, notice = await self._escalation.escalate(
                appeal_id=appeal_id,
                reason=reason,
                summary=content[:500],
            )
            assistant = await self._persistence.add_message(
                appeal_id=appeal_id,
                role=MessageRole.ASSISTANT,
                message_kind=MessageKind.ESCALATION_NOTICE,
                content=notice,
            )
            appeal = await self._persistence.get_appeal(appeal_id) or appeal
            new_messages.append(assistant)

        latency = dict(final.get("latency_ms") or {})
        latency["turn_total_ms"] = round((time.perf_counter() - turn_started) * 1000, 2)
        audit_payload = build_dialogue_turn_audit(
            outcome=outcome,
            node_trace=node_trace,
            specificity=final.get("specificity"),
            clarify_reason=final.get("clarify_reason"),
            escalation_reason=final.get("escalation_reason"),
            citations=citations,
            candidates=list(final.get("candidates") or []),
            rerank_mode=final.get("rerank_mode"),
            rerank_scores=list(final.get("rerank_scores") or []),
            latency_ms=latency,
        )
        await self._persistence.add_audit_event(
            appeal_id=appeal_id,
            event_type="dialogue_turn",
            payload=dict(audit_payload),
        )
        return DialogueTurnResult(
            appeal=appeal,
            messages=new_messages,
            outcome=outcome,
            node_trace=node_trace,
        )
