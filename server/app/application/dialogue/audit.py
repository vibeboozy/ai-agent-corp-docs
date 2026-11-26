"""
ANCHOR: app.application.dialogue.audit
PURPOSE: Schema + builder for dialogue_turn audit_events.payload.
Dependencies: DialogueState / turn outcomes
DO:
- Persist LLM/retrieval latency, rerank scores, answer chunk_ids, clarify/escalate reasons
DONT:
- Put secrets or full document bodies in payload
"""

from __future__ import annotations

from typing import Any, TypedDict


class LatencyPayload(TypedDict, total=False):
    turn_total_ms: float
    llm_assess_ms: float
    llm_complete_ms: float
    retrieval_total_ms: float
    embed_ms: float
    search_ms: float
    rerank_ms: float


class RerankScorePayload(TypedDict, total=False):
    chunk_id: str
    document_id: str
    score: float


class RerankPayload(TypedDict, total=False):
    mode: str
    scores: list[RerankScorePayload]


class DialogueTurnAuditPayload(TypedDict, total=False):
    """Documented shape of audit_events.payload for event_type=dialogue_turn."""

    outcome: str  # clarify | answer | escalate
    node_trace: list[str]
    specificity: str
    clarify_reason: str | None
    escalation_reason: str | None
    chunk_ids: list[str]
    citations: list[dict[str, Any]]
    hit_count: int
    rerank: RerankPayload
    latency_ms: LatencyPayload


def build_dialogue_turn_audit(
    *,
    outcome: str,
    node_trace: list[str],
    specificity: str | None = None,
    clarify_reason: str | None = None,
    escalation_reason: str | None = None,
    citations: list[dict[str, Any]] | None = None,
    candidates: list[dict[str, Any]] | None = None,
    rerank_mode: str | None = None,
    rerank_scores: list[dict[str, Any]] | None = None,
    latency_ms: dict[str, float] | None = None,
) -> DialogueTurnAuditPayload:
    """Assemble a durable audit payload from graph final state + timings."""
    cites = list(citations or [])
    chunk_ids: list[str] = []
    for c in cites:
        cid = c.get("chunk_id")
        if cid is not None and str(cid) not in chunk_ids:
            chunk_ids.append(str(cid))
    if not chunk_ids and candidates:
        for h in candidates:
            cid = h.get("chunk_id")
            if cid is not None and str(cid) not in chunk_ids:
                chunk_ids.append(str(cid))

    scores: list[RerankScorePayload] = []
    for item in rerank_scores or []:
        scores.append(
            {
                "chunk_id": str(item.get("chunk_id") or ""),
                "document_id": str(item.get("document_id") or ""),
                "score": float(item.get("score") or 0.0),
            }
        )

    payload: DialogueTurnAuditPayload = {
        "outcome": outcome,
        "node_trace": list(node_trace or []),
        "chunk_ids": chunk_ids,
        "citations": [
            {
                "chunk_id": c.get("chunk_id"),
                "document_id": c.get("document_id"),
                "score": float(c.get("score") or 0.0),
            }
            for c in cites
        ],
        "hit_count": len(candidates or []),
        "clarify_reason": clarify_reason,
        "escalation_reason": escalation_reason if outcome == "escalate" else None,
    }
    if specificity:
        payload["specificity"] = specificity
    payload["rerank"] = {
        "mode": rerank_mode or "none",
        "scores": scores,
    }
    if latency_ms:
        payload["latency_ms"] = {k: float(v) for k, v in latency_ms.items()}  # type: ignore[assignment]
    return payload
