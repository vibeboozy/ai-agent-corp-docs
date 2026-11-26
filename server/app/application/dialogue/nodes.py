"""
ANCHOR: app.application.dialogue.nodes
PURPOSE: LangGraph node callables (assess, clarify, retrieve, ground, answer, escalate).
Dependencies: retrieval, grounding, quality_escalation, llm port via DI
CRITICAL: Nodes must call ports — never hard-code Http* (CS-LG-02).
DO:
- Same node functions for all DI-wired adapters
DONT:
- Return ungrounded final answers
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.adapters.llm.port import LLMClient
from app.application.dialogue.state import DialogueState
from app.application.grounding.service import GroundingService
from app.application.retrieval.service import RetrievalService


@dataclass
class DialogueDeps:
    llm: LLMClient
    retrieval: RetrievalService
    grounding: GroundingService
    quality_email: str


def _trace(state: DialogueState, node: str) -> list[str]:
    return list(state.get("node_trace") or []) + [node]


def make_nodes(deps: DialogueDeps) -> dict[str, Callable[[DialogueState], Any]]:
    """Build node callables closed over DI ports/services."""

    async def assess_specificity(state: DialogueState) -> DialogueState:
        label = await deps.llm.classify_specificity(
            state.get("user_message", ""),
            history=list(state.get("history") or []),
        )
        return {
            **state,
            "specificity": label,
            "node_trace": _trace(state, f"assess:{label}"),
        }

    async def clarify(state: DialogueState) -> DialogueState:
        turns = int(state.get("clarify_turns") or 0) + 1
        max_turns = int(state.get("max_clarify_turns") or 3)
        if turns > max_turns:
            return {
                **state,
                "clarify_turns": turns,
                "outcome": "escalate",
                "escalation_reason": "max_clarify_exceeded",
                "node_trace": _trace(state, "clarify:max_exceeded"),
            }
        specificity = state.get("specificity") or "underspecified"
        if specificity == "ambiguous":
            text = (
                "Уточните, пожалуйста: речь о договорах на закупку или о договорах "
                "с подрядчиками? От этого зависит применимый регламент."
            )
        else:
            text = (
                "Вопрос сформулирован недостаточно конкретно. Укажите, пожалуйста, "
                "тип процесса (закупка, подряд, отпуск и т.п.) и что именно нужно узнать."
            )
        return {
            **state,
            "clarify_turns": turns,
            "clarification_text": text,
            "outcome": "clarify",
            "node_trace": _trace(state, "clarify"),
        }

    async def retrieve(state: DialogueState) -> DialogueState:
        query = state.get("user_message") or ""
        # Include prior user clarifications for better retrieval context.
        hist = list(state.get("history") or [])
        if hist:
            query = " ".join(hist[-4:] + [query])
        candidates = await deps.retrieval.retrieve(query, limit=5)
        return {
            **state,
            "candidates": candidates,
            "node_trace": _trace(state, f"retrieve:hits={len(candidates)}"),
        }

    async def ground(state: DialogueState) -> DialogueState:
        candidates = list(state.get("candidates") or [])
        draft = None
        if candidates:
            draft = await deps.llm.complete(
                system="Ground answers only in provided chunks.",
                user=f"Q: {state.get('user_message')}\nCHUNK: {candidates[0].get('text')}",
            )
        result = deps.grounding.ground(candidates=candidates, draft=draft)
        if result.ok:
            return {
                **state,
                "grounded": True,
                "draft_answer": result.answer_text or "",
                "citations": result.citations,
                "outcome": "answer",
                "node_trace": _trace(state, "ground:ok"),
            }
        return {
            **state,
            "grounded": False,
            "draft_answer": "",
            "citations": [],
            "outcome": "escalate",
            "escalation_reason": result.reason or "ungrounded",
            "node_trace": _trace(state, f"ground:fail:{result.reason}"),
        }

    async def answer(state: DialogueState) -> DialogueState:
        return {
            **state,
            "outcome": "answer",
            "node_trace": _trace(state, "answer"),
        }

    async def escalate(state: DialogueState) -> DialogueState:
        reason = state.get("escalation_reason") or "no_supporting_chunks"
        return {
            **state,
            "outcome": "escalate",
            "escalation_reason": reason,
            "quality_email": deps.quality_email,
            "node_trace": _trace(state, f"escalate:{reason}"),
        }

    return {
        "assess_specificity": assess_specificity,
        "clarify": clarify,
        "retrieve": retrieve,
        "ground": ground,
        "answer": answer,
        "escalate": escalate,
    }


# Module-level placeholders kept for import compatibility / tests.
async def assess_specificity(state: DialogueState) -> DialogueState:
    raise NotImplementedError("Use make_nodes(deps) — assess_specificity")


async def clarify(state: DialogueState) -> DialogueState:
    raise NotImplementedError("Use make_nodes(deps) — clarify")


async def retrieve(state: DialogueState) -> DialogueState:
    raise NotImplementedError("Use make_nodes(deps) — retrieve")


async def ground(state: DialogueState) -> DialogueState:
    raise NotImplementedError("Use make_nodes(deps) — ground")


async def answer(state: DialogueState) -> DialogueState:
    raise NotImplementedError("Use make_nodes(deps) — answer")


async def escalate(state: DialogueState) -> DialogueState:
    raise NotImplementedError("Use make_nodes(deps) — escalate")
