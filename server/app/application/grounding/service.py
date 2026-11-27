"""
ANCHOR: app.application.grounding.service
PURPOSE: Citation check; refuse unsupported claims (ANC-GROUND-01/02).
Dependencies: domain ChunkCitation; settings thresholds; text_util; answer_format
CRITICAL: Final answers MUST be chunk-supported (ANC-GROUND-01/02).
DO:
- Prefer short human Ответ + authoritative Источник/Цитата from citations
- Refuse or escalate unsupported claims
DONT:
- Treat LLM draft as sole source of truth without chunk overlap
- Dump raw regulation prose as the only user-facing body
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.application.dialogue.answer_format import extract_answer_body, format_human_answer
from app.application.text_util import (
    complete_sentences,
    lexical_overlap,
    quote_at_boundary,
    strip_think_blocks,
)


@dataclass
class GroundingResult:
    ok: bool
    citations: list[dict[str, Any]]
    answer_text: str | None
    reason: str | None = None


class GroundingService:
    """Require min citations above score threshold; build human-readable answers."""

    def __init__(self, *, min_citations: int = 1, min_score: float = 0.0) -> None:
        self._min_citations = min_citations
        self._min_score = min_score

    def ground(
        self,
        *,
        candidates: list[dict[str, Any]],
        draft: str | None = None,
        query: str | None = None,
    ) -> GroundingResult:
        usable = [
            c
            for c in candidates
            if float(c.get("score") or 0.0) >= self._min_score and c.get("text")
        ]
        # Prefer candidates that actually share tokens with the question.
        if query and usable:
            ranked = sorted(
                usable,
                key=lambda c: (
                    lexical_overlap(query, str(c.get("text") or "")),
                    float(c.get("score") or 0.0),
                ),
                reverse=True,
            )
            # Drop near-zero lexical overlap when a better match exists.
            best_lex = lexical_overlap(query, str(ranked[0].get("text") or ""))
            if best_lex > 0:
                usable = [
                    c
                    for c in ranked
                    if lexical_overlap(query, str(c.get("text") or "")) >= best_lex * 0.35
                    or float(c.get("score") or 0.0) >= float(ranked[0].get("score") or 0.0)
                ] or ranked
            else:
                usable = ranked

        if len(usable) < self._min_citations:
            return GroundingResult(
                ok=False,
                citations=[],
                answer_text=None,
                reason="insufficient_citations",
            )

        top = usable[0]
        citations = [
            {
                "document_id": c["document_id"],
                "chunk_id": c["chunk_id"],
                "quote": quote_at_boundary(str(c["text"]), 400),
                "score": float(c.get("score") or 0.0),
                "document_title": c.get("document_title"),
                "locator": c.get("locator") or c.get("section_title"),
            }
            for c in usable[:3]
        ]

        title = str(top.get("document_title") or top["document_id"])
        locator = top.get("locator") or top.get("section_title")
        quote = str(citations[0].get("quote") or top.get("text") or "")
        chunk_text = str(top.get("text") or "")
        # Strip CoT wrappers even if a Fake/bypass LLM skipped HttpLLMClient.complete().
        draft_clean = strip_think_blocks(draft or "")
        answer_body: str | None = None
        # Prefer LLM draft only when it overlaps the supporting chunk (grounded).
        if draft_clean:
            draft_for_overlap = extract_answer_body(draft_clean) or draft_clean
            if lexical_overlap(draft_for_overlap, chunk_text) >= 0.15:
                answer_body = extract_answer_body(draft_clean) or complete_sentences(
                    draft_clean, max_chars=400
                )
        if not answer_body:
            # Fallback: still human template; body is the supporting clause (no long dump prefix).
            answer_body = complete_sentences(chunk_text, max_chars=400)

        answer = format_human_answer(
            answer=answer_body,
            document_title=title,
            locator=str(locator) if locator else None,
            quote=quote,
        )
        return GroundingResult(ok=True, citations=citations, answer_text=answer)
