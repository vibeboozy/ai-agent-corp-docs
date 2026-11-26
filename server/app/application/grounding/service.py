"""
ANCHOR: app.application.grounding.service
PURPOSE: Citation check; refuse unsupported claims (ANC-GROUND-01/02).
Dependencies: domain ChunkCitation; settings thresholds
CRITICAL: Final answers MUST be chunk-supported (ANC-GROUND-01/02).
DO:
- Refuse or escalate unsupported claims
DONT:
- Treat LLM draft as sole source of truth
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class GroundingResult:
    ok: bool
    citations: list[dict[str, Any]]
    answer_text: str | None
    reason: str | None = None


class GroundingService:
    """Require min citations above score threshold; build answer from chunk quotes."""

    def __init__(self, *, min_citations: int = 1, min_score: float = 0.0) -> None:
        self._min_citations = min_citations
        self._min_score = min_score

    def ground(
        self,
        *,
        candidates: list[dict[str, Any]],
        draft: str | None = None,
    ) -> GroundingResult:
        usable = [
            c
            for c in candidates
            if float(c.get("score") or 0.0) >= self._min_score and c.get("text")
        ]
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
                "quote": str(c["text"])[:400],
                "score": float(c.get("score") or 0.0),
                "document_title": c.get("document_title"),
                "locator": c.get("locator"),
            }
            for c in usable[:3]
        ]
        # Prefer draft only if it does not invent beyond chunk (stub: use chunk text).
        _ = draft
        answer = f"Согласно регламенту «{top.get('document_title') or top['document_id']}»: {top['text']}"
        return GroundingResult(ok=True, citations=citations, answer_text=answer)
