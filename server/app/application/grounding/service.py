"""
ANCHOR: app.application.grounding.service
PURPOSE: Citation check; refuse unsupported claims (ANC-GROUND-01/02).
Dependencies: domain ChunkCitation; settings thresholds; text_util; answer_format; glossary
CRITICAL: Final answers MUST be chunk-supported (ANC-GROUND-01/02).
DO:
- Prefer short human WHO/WHAT/WHEN paraphrase + authoritative Источник/Цитата
- Expand known abbreviations in Ответ when glossary active
- Refuse or escalate unsupported claims
DONT:
- Dump / truncate regulation prose as Ответ
- Put full clause text into Источник
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.application.dialogue.answer_format import (
    enforce_short_paraphrase,
    extract_answer_body,
    format_human_answer,
    needs_paraphrase_repair,
    normalize_locator,
)
from app.application.text_util import (
    lexical_overlap,
    quote_at_boundary,
    strip_think_blocks,
)
from app.domain.glossary import AbbreviationGlossary


@dataclass
class GroundingResult:
    ok: bool
    citations: list[dict[str, Any]]
    answer_text: str | None
    reason: str | None = None
    needs_repair: bool = False


class GroundingService:
    """Require min citations above score threshold; build human-readable answers."""

    def __init__(
        self,
        *,
        min_citations: int = 1,
        min_score: float = 0.0,
        glossary: AbbreviationGlossary | None = None,
    ) -> None:
        self._min_citations = min_citations
        self._min_score = min_score
        self._glossary = glossary

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
        if query and usable:
            ranked = sorted(
                usable,
                key=lambda c: (
                    lexical_overlap(query, str(c.get("text") or "")),
                    float(c.get("score") or 0.0),
                ),
                reverse=True,
            )
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
        citations = []
        for c in usable[:3]:
            point = normalize_locator(
                str(c.get("locator") or c.get("section_title") or "")
            )
            citations.append(
                {
                    "document_id": c["document_id"],
                    "chunk_id": c["chunk_id"],
                    "quote": quote_at_boundary(str(c["text"]), 400),
                    "score": float(c.get("score") or 0.0),
                    "document_title": c.get("document_title"),
                    # Point number only — never the full clause sentence.
                    "locator": point,
                }
            )

        title = str(top.get("document_title") or top["document_id"])
        raw_locator = top.get("locator") or top.get("section_title")
        locator = normalize_locator(str(raw_locator) if raw_locator else None)
        quote = str(citations[0].get("quote") or top.get("text") or "")
        chunk_text = str(top.get("text") or "")
        draft_clean = strip_think_blocks(draft or "")
        answer_body = ""
        if draft_clean:
            draft_for_overlap = extract_answer_body(draft_clean) or draft_clean
            if lexical_overlap(draft_for_overlap, chunk_text) >= 0.15:
                answer_body = enforce_short_paraphrase(
                    draft_clean, query=query or "", quote=quote
                )
        if not answer_body:
            answer_body = enforce_short_paraphrase(
                chunk_text, query=query or "", quote=quote
            )

        answer = format_human_answer(
            answer=answer_body,
            document_title=title,
            locator=locator,
            quote=quote,
            query=query or "",
            glossary=self._glossary,
        )
        if not answer:
            # Extraction failed — caller should regenerate a short paraphrase.
            return GroundingResult(
                ok=False,
                citations=citations,
                answer_text=None,
                needs_repair=True,
                reason="paraphrase_required",
            )
        final_body = extract_answer_body(answer) or ""
        return GroundingResult(
            ok=True,
            citations=citations,
            answer_text=answer,
            needs_repair=needs_paraphrase_repair(final_body, quote=quote),
        )
