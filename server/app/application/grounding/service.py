"""
ANCHOR: app.application.grounding.service
PURPOSE: Citation check; refuse unsupported claims (ANC-GROUND-01/02).
Dependencies: domain ChunkCitation; settings thresholds; text_util; answer_format; glossary
CRITICAL: Final answers MUST be chunk-supported (ANC-GROUND-01/02).
DO:
- Prefer short human WHO/WHAT/WHEN paraphrase + authoritative Источник/Цитата
- Expand known abbreviations in Ответ when glossary active
- Refuse or escalate unsupported / irrelevant / weak hits
DONT:
- Dump / truncate regulation prose as Ответ
- Put full clause text into Источник
- Answer from a quote that does not address the question
"""

from __future__ import annotations

import re
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
    lexical_relevance,
    quote_at_boundary,
    strip_think_blocks,
    tokenize,
)
from app.domain.glossary import AbbreviationGlossary

# Context-poor HybridChunker fragments (≈2–3 words) cannot ground a real answer.
# Keep this low so short but complete clauses (5–6 tokens) still ground.
_MIN_CHUNK_TOKENS = 4
_WHEN_ASK_RE = re.compile(
    r"(?i)\b(срок|когда|в\s+какой\s+срок|как\s+быстро)\b"
)
_TEMPORAL_CUE_RE = re.compile(
    r"(?i)(?:в\s+течение|не\s+позднее|\d+\s+рабоч|\d+\s+календарн)"
)


@dataclass
class GroundingResult:
    ok: bool
    citations: list[dict[str, Any]]
    answer_text: str | None
    reason: str | None = None
    needs_repair: bool = False


class GroundingService:
    """Require min citations above score + query relevance; build human answers."""

    def __init__(
        self,
        *,
        min_citations: int = 1,
        min_score: float = 0.0,
        min_query_overlap: float = 0.12,
        glossary: AbbreviationGlossary | None = None,
    ) -> None:
        self._min_citations = min_citations
        self._min_score = min_score
        self._min_query_overlap = max(0.0, float(min_query_overlap))
        self._glossary = glossary

    def _chunk_too_small(self, text: str) -> bool:
        return len(tokenize(text)) < _MIN_CHUNK_TOKENS

    @staticmethod
    def _when_ask(query: str | None) -> bool:
        return bool(_WHEN_ASK_RE.search(query or ""))

    @staticmethod
    def _has_temporal_cue(text: str) -> bool:
        return bool(_TEMPORAL_CUE_RE.search(text or ""))

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
            if float(c.get("score") or 0.0) >= self._min_score
            and c.get("text")
            and not self._chunk_too_small(str(c.get("text") or ""))
        ]
        # Skip relevance gate when the query has no content tokens (e.g. "q" in unit tests).
        query_tokens = tokenize(query) if query else []
        apply_query_gate = bool(query_tokens) and self._min_query_overlap > 0
        when_ask = self._when_ask(query)

        if apply_query_gate and usable:
            ranked = sorted(
                usable,
                key=lambda c: (
                    # WHEN questions: prefer clauses that actually state a deadline.
                    (
                        1
                        if when_ask and self._has_temporal_cue(str(c.get("text") or ""))
                        else 0
                    ),
                    lexical_relevance(query or "", str(c.get("text") or "")),
                    float(c.get("score") or 0.0),
                ),
                reverse=True,
            )
            best_rel = lexical_relevance(query or "", str(ranked[0].get("text") or ""))
            # Weak / off-topic hits (e.g. budget approval for a margin-% question)
            # must escalate — never become a grounded "answer".
            if best_rel < self._min_query_overlap:
                return GroundingResult(
                    ok=False,
                    citations=[],
                    answer_text=None,
                    reason="irrelevant_citations",
                )
            usable = [
                c
                for c in ranked
                if lexical_relevance(query or "", str(c.get("text") or ""))
                >= max(self._min_query_overlap, best_rel * 0.35)
                or float(c.get("score") or 0.0) >= float(ranked[0].get("score") or 0.0)
            ] or ranked
            # Keep only passages that still clear the query-relevance floor.
            usable = [
                c
                for c in usable
                if lexical_relevance(query or "", str(c.get("text") or ""))
                >= self._min_query_overlap
            ] or []
            # WHEN with only neighbor passages (no deadline span) → escalate, do not
            # invent a false Ответ / hit paraphrase_required on an off-topic quote.
            if when_ask and usable and not any(
                self._has_temporal_cue(str(c.get("text") or "")) for c in usable
            ):
                return GroundingResult(
                    ok=False,
                    citations=[],
                    answer_text=None,
                    reason="irrelevant_citations",
                )

        if len(usable) < self._min_citations:
            # Distinguish empty/weak score pool from topical mismatch when possible.
            scored = [
                c
                for c in candidates
                if float(c.get("score") or 0.0) >= self._min_score and c.get("text")
            ]
            reason = "insufficient_citations"
            if apply_query_gate and scored and not usable:
                # All scored hits were tiny or below query-overlap.
                any_rel = max(
                    (
                        lexical_relevance(query or "", str(c.get("text") or ""))
                        for c in scored
                    ),
                    default=0.0,
                )
                if any_rel < self._min_query_overlap:
                    reason = "irrelevant_citations"
            return GroundingResult(
                ok=False,
                citations=[],
                answer_text=None,
                reason=reason,
            )

        draft_clean = strip_think_blocks(draft or "")
        draft_for_overlap = (
            extract_answer_body(draft_clean) or draft_clean if draft_clean else ""
        )
        # Prefer the usable chunk that actually supports the draft (or temporal cue),
        # not merely retrieval rank — near-duplicate questions otherwise cite a neighbor.
        def _support_key(c: dict[str, Any]) -> tuple[float, float, float]:
            text = str(c.get("text") or "")
            draft_hit = (
                lexical_overlap(draft_for_overlap, text) if draft_for_overlap else 0.0
            )
            return (
                draft_hit,
                1.0 if when_ask and self._has_temporal_cue(text) else 0.0,
                lexical_relevance(query or "", text) if apply_query_gate else 0.0,
            )

        top = max(usable, key=_support_key)
        # Stable citation order: supporting top first, then remaining by support.
        ordered = [top] + [c for c in usable if c is not top]
        citations = []
        for c in ordered[:3]:
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
        query_rel = (
            lexical_relevance(query or "", chunk_text) if apply_query_gate else 1.0
        )
        answer_body = ""
        if draft_clean and draft_for_overlap:
            if lexical_overlap(draft_for_overlap, chunk_text) >= 0.15:
                answer_body = enforce_short_paraphrase(
                    draft_clean, query=query or "", quote=quote
                )
        # Only invent an Ответ from the chunk when it is actually about the question.
        # UNSUPPORTED / missing draft + off-topic quote → escalate (not a false answer).
        if not answer_body:
            if (not apply_query_gate) or query_rel >= self._min_query_overlap:
                answer_body = enforce_short_paraphrase(
                    chunk_text, query=query or "", quote=quote
                )
            else:
                return GroundingResult(
                    ok=False,
                    citations=citations,
                    answer_text=None,
                    reason="irrelevant_citations",
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
        # Final guard: quote/answer must still be about the question.
        if apply_query_gate and query_rel < self._min_query_overlap:
            return GroundingResult(
                ok=False,
                citations=citations,
                answer_text=None,
                reason="irrelevant_citations",
            )
        return GroundingResult(
            ok=True,
            citations=citations,
            answer_text=answer,
            needs_repair=needs_paraphrase_repair(final_body, quote=quote),
        )
