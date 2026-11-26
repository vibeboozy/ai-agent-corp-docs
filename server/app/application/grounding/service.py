"""
ANCHOR: app.application.grounding.service
PURPOSE: Citation check; refuse unsupported claims (ANC-GROUND-01/02).
Dependencies: domain ChunkCitation; settings thresholds; text_util
CRITICAL: Final answers MUST be chunk-supported (ANC-GROUND-01/02).
DO:
- Prefer complete-sentence answers over raw mid-chunk quote stubs
- Refuse or escalate unsupported claims
DONT:
- Treat LLM draft as sole source of truth without chunk overlap
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.application.text_util import complete_sentences, lexical_overlap, quote_at_boundary


@dataclass
class GroundingResult:
    ok: bool
    citations: list[dict[str, Any]]
    answer_text: str | None
    reason: str | None = None


class GroundingService:
    """Require min citations above score threshold; build complete-sentence answers."""

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

        title = top.get("document_title") or top["document_id"]
        chunk_text = complete_sentences(str(top.get("text") or ""), max_chars=900)
        draft_clean = (draft or "").strip()
        # Prefer LLM draft only when it overlaps the supporting chunk (grounded).
        if draft_clean and lexical_overlap(draft_clean, str(top.get("text") or "")) >= 0.15:
            answer = complete_sentences(draft_clean, max_chars=900)
        else:
            answer = f"Согласно регламенту «{title}»: {chunk_text}"
        return GroundingResult(ok=True, citations=citations, answer_text=answer)
