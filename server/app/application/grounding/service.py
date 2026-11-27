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
    extract_short_paraphrase,
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

# Context-poor fragments (<4 content tokens) cannot ground a real answer.
# Checklist orphans («1. подписан договор…;») are caught by list-item / trailing-;
# rules below — do not raise the floor so short complete clauses still ground.
_MIN_CHUNK_TOKENS = 4
# Bare numbered list item («1. …») — not a multipart clause («9.5. …»).
_LIST_ITEM_RE = re.compile(r"^\d+\.(?!\d)\s+")
_WHEN_ASK_RE = re.compile(
    r"(?i)\b(срок|когда|в\s+какой\s+срок|как\s+быстро|за\s+сколько|сколько\s+рабоч)\b"
)
_WHO_ASK_RE = re.compile(r"(?i)\bкто\b")
_TEMPORAL_CUE_RE = re.compile(
    r"(?i)(?:в\s+течение|не\s+позднее|не\s+менее\s+чем\s+за|\d+\s+рабоч|\d+\s+календарн)"
)
_WHO_AGENCY_RE = re.compile(
    r"(?i)(?:заключа(?:ются|ется)\s+от|подписыва(?:ют|ет)|отвечает|назначает|"
    r"утверждает|согласовывает|планирует|ведёт|является)"
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

    def _chunk_too_weak(self, text: str) -> bool:
        """Reject tiny / checklist orphans that survived untitled-only HybridChunker merge."""
        raw = (text or "").strip()
        toks = tokenize(raw)
        if len(toks) < _MIN_CHUNK_TOKENS:
            return True
        # «подписан договор на услуги с заказчиком;» — list fragment, not a clause.
        if raw.endswith(";") and len(toks) < 14:
            return True
        if _LIST_ITEM_RE.match(raw) and len(toks) < 14:
            return True
        return False

    @staticmethod
    def _when_ask(query: str | None) -> bool:
        return bool(_WHEN_ASK_RE.search(query or ""))

    @staticmethod
    def _who_ask(query: str | None) -> bool:
        return bool(_WHO_ASK_RE.search(query or ""))

    @staticmethod
    def _has_temporal_cue(text: str) -> bool:
        return bool(_TEMPORAL_CUE_RE.search(text or ""))

    @staticmethod
    def _has_who_agency(text: str) -> bool:
        return bool(_WHO_AGENCY_RE.search(text or ""))

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
            and not self._chunk_too_weak(str(c.get("text") or ""))
        ]
        # Skip relevance gate when the query has no content tokens (e.g. "q" in unit tests).
        query_tokens = tokenize(query) if query else []
        apply_query_gate = bool(query_tokens) and self._min_query_overlap > 0
        when_ask = self._when_ask(query)
        who_ask = self._who_ask(query)

        if apply_query_gate and usable:
            ranked = sorted(
                usable,
                key=lambda c: (
                    # WHEN: prefer clauses that state a deadline.
                    (
                        1
                        if when_ask and self._has_temporal_cue(str(c.get("text") or ""))
                        else 0
                    ),
                    # WHO: prefer agency clauses over checklist noise.
                    (
                        1
                        if who_ask and self._has_who_agency(str(c.get("text") or ""))
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
            # WHEN with only neighbor passages (no deadline span) → escalate.
            if when_ask and usable and not any(
                self._has_temporal_cue(str(c.get("text") or "")) for c in usable
            ):
                return GroundingResult(
                    ok=False,
                    citations=[],
                    answer_text=None,
                    reason="irrelevant_citations",
                )
            # WHO: do not hard-require agency verbs (valid «планирует» / role clauses vary);
            # ranking + weak-chunk reject + extract loop handle checklist junk.

        if len(usable) < self._min_citations:
            # Distinguish empty/weak score pool from topical mismatch when possible.
            scored = [
                c
                for c in candidates
                if float(c.get("score") or 0.0) >= self._min_score and c.get("text")
            ]
            reason = "insufficient_citations"
            if apply_query_gate and scored and not usable:
                # All scored hits were tiny/weak or below query-overlap.
                any_rel = max(
                    (
                        lexical_relevance(query or "", str(c.get("text") or ""))
                        for c in scored
                        if not self._chunk_too_weak(str(c.get("text") or ""))
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

        def _support_key(c: dict[str, Any]) -> tuple[float, ...]:
            text = str(c.get("text") or "")
            draft_hit = (
                lexical_overlap(draft_for_overlap, text) if draft_for_overlap else 0.0
            )
            extract_hit = 1.0 if extract_short_paraphrase(query or "", text) else 0.0
            return (
                extract_hit,
                draft_hit,
                1.0 if when_ask and self._has_temporal_cue(text) else 0.0,
                1.0 if who_ask and self._has_who_agency(text) else 0.0,
                lexical_relevance(query or "", text) if apply_query_gate else 0.0,
                float(len(tokenize(text))),
            )

        ordered = sorted(usable, key=_support_key, reverse=True)

        # Try candidates in support order until a short paraphrase grounds.
        last_citations: list[dict[str, Any]] = []
        for top in ordered:
            citations: list[dict[str, Any]] = []
            for c in [top] + [x for x in ordered if x is not top]:
                if len(citations) >= 3:
                    break
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
                        "locator": point,
                    }
                )
            last_citations = citations

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
            if not answer_body:
                if (not apply_query_gate) or query_rel >= self._min_query_overlap:
                    answer_body = enforce_short_paraphrase(
                        chunk_text, query=query or "", quote=quote
                    )
                else:
                    continue

            if not answer_body:
                continue

            answer = format_human_answer(
                answer=answer_body,
                document_title=title,
                locator=locator,
                quote=quote,
                query=query or "",
                glossary=self._glossary,
            )
            if not answer:
                continue
            final_body = extract_answer_body(answer) or ""
            if apply_query_gate and query_rel < self._min_query_overlap:
                continue
            if needs_paraphrase_repair(final_body, quote=quote, query=query or ""):
                continue
            return GroundingResult(
                ok=True,
                citations=citations,
                answer_text=answer,
                needs_repair=False,
            )

        return GroundingResult(
            ok=False,
            citations=last_citations,
            answer_text=None,
            needs_repair=True,
            reason="paraphrase_required",
        )
