"""
ANCHOR: app.application.dialogue.nodes
PURPOSE: LangGraph node callables (assess, refuse, clarify, retrieve, ground, answer, escalate).
Dependencies: retrieval, grounding, quality_escalation, llm port via DI
CRITICAL: Nodes must call ports — never hard-code Http* (CS-LG-02).
DO:
- Same node functions for all DI-wired adapters
- Record LLM/retrieval latency and clarify/escalate reasons for audit
- Refuse off-topic chitchat; clarifications via LLM (no hardcoded RU templates)
DONT:
- Return ungrounded final answers
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from app.adapters.llm.port import LLMClient
from app.application.dialogue.answer_format import (
    build_answer_system_prompt,
    build_answer_user_prompt,
    build_paraphrase_repair_prompt,
    extract_answer_body,
    needs_paraphrase_repair,
)
from app.application.dialogue.offtopic import (
    OFF_TOPIC_REFUSAL_RU,
    is_off_topic,
    is_supported_domain,
)
from app.application.dialogue.specificity import prefer_specific_label
from app.application.dialogue.state import DialogueState
from app.application.grounding.service import GroundingService
from app.application.retrieval.service import RetrievalService
from app.application.text_util import strip_think_blocks
from app.domain.allowed_topics import (
    AllowedTopic,
    build_refusal_message,
    format_topics_for_prompt,
    resolve_allowed_topics,
)

logger = logging.getLogger(__name__)


@dataclass
class DialogueDeps:
    llm: LLMClient
    retrieval: RetrievalService
    grounding: GroundingService
    quality_email: str
    allowed_topics: list[AllowedTopic] = field(default_factory=resolve_allowed_topics)


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
        user_message = state.get("user_message", "") or ""
        history = list(state.get("history") or [])
        topics = list(deps.allowed_topics)
        if is_off_topic(user_message, history, allowed_topics=topics):
            assess_ms = round((time.perf_counter() - t0) * 1000, 2)
            logger.info("classify_specificity off_topic message=%r", user_message[:200])
            return {
                **state,
                "specificity": "off_topic",
                "raw_specificity": "off_topic",
                "latency_ms": _merge_latency(state, llm_assess_ms=assess_ms),
                "node_trace": _trace(state, "assess:off_topic"),
            }
        raw_label = await deps.llm.classify_specificity(user_message, history=history)
        raw_norm = str(raw_label or "").strip().lower()
        # Conservative: role+topic / allowed-topic questions must retrieve (not refuse),
        # even when the LLM timidly returns underspecified/ambiguous/off_topic.
        if raw_norm == "off_topic":
            if is_supported_domain(user_message, allowed_topics=topics):
                label = prefer_specific_label("specific", user_message, history)
            elif prefer_specific_label("underspecified", user_message, history) == "specific":
                label = "specific"
            else:
                label = "off_topic"
        else:
            label = prefer_specific_label(raw_label, user_message, history)
        assess_ms = round((time.perf_counter() - t0) * 1000, 2)
        logger.info(
            "classify_specificity raw=%r final=%r message=%r",
            raw_label,
            label,
            user_message[:200],
        )
        trace = f"assess:{label}(raw:{raw_label})"
        return {
            **state,
            "specificity": label,
            "raw_specificity": str(raw_label),
            "latency_ms": _merge_latency(state, llm_assess_ms=assess_ms),
            "node_trace": _trace(state, trace),
        }

    async def refuse(state: DialogueState) -> DialogueState:
        refusal = build_refusal_message(list(deps.allowed_topics)) or OFF_TOPIC_REFUSAL_RU
        return {
            **state,
            "outcome": "refuse",
            "clarification_text": refusal,
            "draft_answer": refusal,
            "node_trace": _trace(state, "refuse:off_topic"),
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
            hint = (
                "The question maps to multiple regulation scopes. Ask which scope "
                "the user means (one short Russian clarifying question)."
            )
        else:
            reason = "underspecified"
            hint = (
                "The question is underspecified. Ask for the missing process/topic "
                "so retrieval can run (one short Russian clarifying question)."
            )
        hist = "\n".join(list(state.get("history") or [])[-4:])
        user_message = state.get("user_message") or ""
        t0 = time.perf_counter()
        topics_block = format_topics_for_prompt(list(deps.allowed_topics))
        text = await deps.llm.complete(
            system=(
                "You are a grounded assistant for these in-domain topics:\n"
                f"{topics_block}\n"
                "Reply with ONLY the clarifying question in Russian — no preamble."
            ),
            user=(
                f"{hint}\n"
                f"Reason: {reason}\n"
                f"History:\n{hist}\n"
                f"Question:\n{user_message}"
            ),
            temperature=0.2,
        )
        clarify_ms = round((time.perf_counter() - t0) * 1000, 2)
        text = strip_think_blocks(text or "") or (
            "Уточните, пожалуйста, тему и что именно нужно узнать."
        )
        return {
            **state,
            "clarify_turns": turns,
            "clarification_text": text,
            "clarify_reason": reason,
            "outcome": "clarify",
            "latency_ms": _merge_latency(state, llm_clarify_ms=clarify_ms),
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
        user_message = state.get("user_message") or ""
        draft = None
        complete_ms = 0.0
        if candidates:
            # Provide several complete-ish chunks; ask for a full-sentence answer.
            passages = []
            for idx, c in enumerate(candidates[:3]):
                loc = c.get("locator") or c.get("section_title") or ""
                passages.append(
                    f"[{idx}] ({loc}) {c.get('text')}"
                )
            t0 = time.perf_counter()
            topics_block = format_topics_for_prompt(list(deps.allowed_topics))
            draft = await deps.llm.complete(
                system=build_answer_system_prompt(topics_block),
                user=build_answer_user_prompt(
                    question=user_message, passages=passages
                ),
            )
            complete_ms = round((time.perf_counter() - t0) * 1000, 2)
            # Fake LLM ports may skip HttpLLMClient; strip before UNSUPPORTED / ground.
            draft = strip_think_blocks(draft or "") or None
            if draft and "UNSUPPORTED" in draft.upper() and len(draft.strip()) < 40:
                draft = None
        result = deps.grounding.ground(
            candidates=candidates, draft=draft, query=user_message
        )
        # If Ответ is still a regulation dump / mid-clause cut, regenerate a short paraphrase.
        quote = str((result.citations or [{}])[0].get("quote") or "")
        if not quote and candidates:
            quote = str(candidates[0].get("text") or "")
        final_body = extract_answer_body(result.answer_text or "") or ""
        if candidates and (
            not result.ok
            or not result.answer_text
            or result.needs_repair
            or needs_paraphrase_repair(final_body, quote=quote)
        ):
            bad = final_body or extract_answer_body(draft or "") or (draft or "")[:240]
            t1 = time.perf_counter()
            repaired = await deps.llm.complete(
                system=build_answer_system_prompt(
                    format_topics_for_prompt(list(deps.allowed_topics))
                ),
                user=build_paraphrase_repair_prompt(
                    question=user_message,
                    quote=quote,
                    bad_answer=bad or "regulation dump",
                ),
            )
            complete_ms = round(complete_ms + (time.perf_counter() - t1) * 1000, 2)
            repaired = strip_think_blocks(repaired or "") or None
            if repaired and "UNSUPPORTED" not in (repaired or "").upper():
                repaired_result = deps.grounding.ground(
                    candidates=candidates, draft=repaired, query=user_message
                )
                if repaired_result.ok and repaired_result.answer_text:
                    result = repaired_result
                elif not result.ok and repaired_result.citations:
                    # Keep citations for escalation context when first pass had none usable.
                    result = repaired_result
        latency = _merge_latency(state, llm_complete_ms=complete_ms) if candidates else dict(
            state.get("latency_ms") or {}
        )
        if result.ok and result.answer_text:
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
            "citations": list(result.citations or []),
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
        "refuse": refuse,
        "clarify": clarify,
        "retrieve": retrieve,
        "ground": ground,
        "answer": answer,
        "escalate": escalate,
    }


# Module-level placeholders kept for import compatibility / tests.
async def assess_specificity(state: DialogueState) -> DialogueState:
    raise NotImplementedError("Use make_nodes(deps) — assess_specificity")


async def refuse(state: DialogueState) -> DialogueState:
    raise NotImplementedError("Use make_nodes(deps) — refuse")


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
