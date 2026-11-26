"""
ANCHOR: app.application.dialogue.nodes
PURPOSE: LangGraph node callables (assess, clarify, retrieve, ground, answer, escalate).
Dependencies: retrieval, grounding, quality_escalation, llm port via DI
CRITICAL: Nodes must call ports — never hard-code Http* (CS-LG-02).
DO:
- Same node functions for all DI-wired adapters
- Record LLM/retrieval latency and clarify/escalate reasons for audit
DONT:
- Return ungrounded final answers
"""

from __future__ import annotations

import time
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


def _merge_latency(state: DialogueState, **parts: float) -> dict[str, float]:
    out = dict(state.get("latency_ms") or {})
    for key, value in parts.items():
        out[key] = float(value)
    return out


def make_nodes(deps: DialogueDeps) -> dict[str, Callable[[DialogueState], Any]]:
    """Build node callables closed over DI ports/services."""

    async def assess_specificity(state: DialogueState) -> DialogueState:
        t0 = time.perf_counter()
        label = await deps.llm.classify_specificity(
            state.get("user_message", ""),
            history=list(state.get("history") or []),
        )
        assess_ms = round((time.perf_counter() - t0) * 1000, 2)
        return {
            **state,
            "specificity": label,
            "latency_ms": _merge_latency(state, llm_assess_ms=assess_ms),
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
                "clarify_reason": "max_clarify_exceeded",
                "escalation_reason": "max_clarify_exceeded",
                "node_trace": _trace(state, "clarify:max_exceeded"),
            }
        specificity = state.get("specificity") or "underspecified"
        if specificity == "ambiguous":
            reason = "ambiguous"
            text = (
                "Уточните, пожалуйста: речь о договорах на закупку или о договорах "
                "с подрядчиками? От этого зависит применимый регламент."
            )
        else:
            reason = "underspecified"
            text = (
                "Вопрос сформулирован недостаточно конкретно. Укажите, пожалуйста, "
                "тип процесса (закупка, подряд, отпуск и т.п.) и что именно нужно узнать."
            )
        return {
            **state,
            "clarify_turns": turns,
            "clarification_text": text,
            "clarify_reason": reason,
            "outcome": "clarify",
            "node_trace": _trace(state, f"clarify:{reason}"),
        }

    async def retrieve(state: DialogueState) -> DialogueState:
        query = state.get("user_message") or ""
        # Include prior user clarifications for better retrieval context.
        hist = list(state.get("history") or [])
        if hist:
            query = " ".join(hist[-4:] + [query])
        result = await deps.retrieval.retrieve_with_meta(query, limit=5)
        return {
            **state,
            "candidates": result.hits,
            "rerank_mode": result.rerank_mode,
            "rerank_scores": result.rerank_scores,
            "latency_ms": _merge_latency(state, **result.latency_ms),
            "node_trace": _trace(state, f"retrieve:hits={len(result.hits)}"),
        }

    async def ground(state: DialogueState) -> DialogueState:
        candidates = list(state.get("candidates") or [])
        draft = None
        complete_ms = 0.0
        if candidates:
            t0 = time.perf_counter()
            draft = await deps.llm.complete(
                system="Ground answers only in provided chunks.",
                user=f"Q: {state.get('user_message')}\nCHUNK: {candidates[0].get('text')}",
            )
            complete_ms = round((time.perf_counter() - t0) * 1000, 2)
        result = deps.grounding.ground(candidates=candidates, draft=draft)
        latency = _merge_latency(state, llm_complete_ms=complete_ms) if candidates else dict(
            state.get("latency_ms") or {}
        )
        if result.ok:
            return {
                **state,
                "grounded": True,
                "draft_answer": result.answer_text or "",
                "citations": result.citations,
                "outcome": "answer",
                "latency_ms": latency,
                "node_trace": _trace(state, "ground:ok"),
            }
        return {
            **state,
            "grounded": False,
            "draft_answer": "",
            "citations": [],
            "outcome": "escalate",
            "escalation_reason": result.reason or "ungrounded",
            "latency_ms": latency,
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
