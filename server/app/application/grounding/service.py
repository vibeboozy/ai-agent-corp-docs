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
    r"(?i)\b("
    r"срок|когда|в\s+какой\s+срок|как\s+быстро|за\s+сколько|сколько\s+рабоч|"
    r"за\s+какой\s+срок|рабочих\s+дн|sla"
    r")\b"
)
_WHO_ASK_RE = re.compile(r"(?i)\bкто\b")
_TEMPORAL_CUE_RE = re.compile(
    r"(?i)(?:в\s+течение|не\s+позднее|не\s+менее\s+чем\s+за|\d+\s+рабоч|\d+\s+календарн)"
)
_WHO_AGENCY_RE = re.compile(
    r"(?i)(?:заключа(?:ются|ется)\s+от|подписыва(?:ют|ет)|отвечает|назначает|"
    r"утверждает|согласовывает|планирует|ведёт|является)"
)
# Lead-time WHEN («за сколько… инициировать заявку… пресейл») vs wait/timeout neighbors.
_LEAD_TIME_ASK_RE = re.compile(
    r"(?iu)(?:иници\w+|не\s+менее\s+чем|пресейл)"
)
_LEAD_TIME_CLAUSE_RE = re.compile(
    r"(?iu)(?:не\s+менее\s+чем\s+за|иници\w+.{0,48}заявк|заявк\w*.{0,64}иници)"
)
_WAIT_TIMEOUT_CLAUSE_RE = re.compile(
    r"(?iu)(?:не\s+поступа|не\s+обновлял|жду\s+доп|дисквалифицир|"
    r"не\s+более\s+\d+\s+рабоч)"
)
# Purchase WHO («на закупку») — prefer agency/subcontract over DS/AM signing.
_PURCHASE_ASK_RE = re.compile(r"(?iu)\bзакупк")
_PURCHASE_AGENCY_CLAUSE_RE = re.compile(
    r"(?iu)(?:субподрядн|закупк|юридическ\w*\s+лиц|"
    r"заключа(?:ются|ется)\s+от)"
)
_DS_SIGNING_NOISE_RE = re.compile(
    r"(?iu)(?:\bдс\b|дополнительн\w*\s+соглашен|"
    r"ам\s*/\s*менеджер.{0,60}подписыва|подписыва\w*\s+дс)"
)
# WHEN boilerplate — stripped when comparing topical content (SLA vs neighbor deadline).
_WHEN_QUERY_STOP = frozenset(
    {
        "какой",
        "какая",
        "какие",
        "каков",
        "сколько",
        "за",
        "в",
        "на",
        "при",
        "по",
        "с",
        "со",
        "о",
        "об",
        "срок",
        "срока",
        "сроке",
        "когда",
        "рабочих",
        "рабочий",
        "рабочие",
        "дней",
        "дня",
        "днях",
        "день",
        "точный",
        "точно",
        "необходимо",
        "нужно",
        "течение",
        "календарных",
        "календарный",
    }
)


@dataclass
class GroundingResult:
    ok: bool
    citations: list[dict[str, Any]]
    answer_text: str | None
    reason: str | None = None
    needs_repair: bool = False


def _norm_cite_text(value: str | None) -> str:
    """Collapse whitespace for citation identity (learned re-asks often share quotes)."""
    return " ".join(str(value or "").split()).casefold()


def dedupe_citations(
    citations: list[dict[str, Any]],
    *,
    max_n: int = 3,
) -> list[dict[str, Any]]:
    """
    Unique citations for the UI block «Источники и цитаты».

    Keys (in order): chunk_id; then document_id + locator + quote; then quote alone
    so identical learned chunks from separate ingest jobs (different document_id)
    collapse to one entry matching the canonical Ответ/Источник/Цитата form.
    """
    seen_chunk: set[str] = set()
    seen_doc_key: set[tuple[str, str, str]] = set()
    seen_quote: set[str] = set()
    out: list[dict[str, Any]] = []
    for c in citations:
        if len(out) >= max_n:
            break
        chunk_id = str(c.get("chunk_id") or "").strip()
        if chunk_id and chunk_id in seen_chunk:
            continue
        doc = str(c.get("document_id") or "").strip()
        loc = _norm_cite_text(str(c.get("locator") or ""))
        quote = _norm_cite_text(str(c.get("quote") or ""))
        quote_key = quote[:240] if quote else ""
        doc_key = (doc, loc, quote_key)
        if doc_key in seen_doc_key:
            continue
        if quote_key and quote_key in seen_quote:
            continue
        if chunk_id:
            seen_chunk.add(chunk_id)
        seen_doc_key.add(doc_key)
        if quote_key:
            seen_quote.add(quote_key)
        out.append(c)
    return out


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

    @staticmethod
    def _rel(query: str, c: dict[str, Any]) -> float:
        """Body-only relevance for gates (titles shared across a doc must not inflate)."""
        return lexical_relevance(query, str(c.get("text") or ""))

    @classmethod
    def _content_rel(cls, query: str, c: dict[str, Any]) -> float:
        """Relevance on non-WHEN query tokens (distinguishes SLA/подрядчик vs bare deadline)."""
        kept = [t for t in tokenize(query) if t not in _WHEN_QUERY_STOP]
        if not kept:
            return cls._rel(query, c)
        return lexical_relevance(" ".join(kept), str(c.get("text") or ""))

    @staticmethod
    def _org_title_boost(query: str | None, c: dict[str, Any]) -> float:
        """
        Ranking-only: prefer the doc whose title names an org cue from the query.

        E.g. «…пресейл ДБРЦТ» → «Проектная деятельность ДБРЦТ». Do not use the
        whole title for overlap gates (every Presale hit says «Дирекции ИБ»).
        """
        q = (query or "").lower().replace("ё", "е")
        title = str(c.get("document_title") or "").lower().replace("ё", "е")
        if not q or not title:
            return 0.0
        boost = 0.0
        for cue in ("дбрцт", "дирекции иб", "тех дирек"):
            if cue in q and cue in title:
                boost = max(boost, 1.0 if cue == "дбрцт" else 0.5)
        return boost

    @staticmethod
    def _lead_time_ask(query: str | None) -> bool:
        q = query or ""
        return bool(_WHEN_ASK_RE.search(q) and _LEAD_TIME_ASK_RE.search(q))

    @staticmethod
    def _is_lead_time_clause(text: str) -> bool:
        return bool(_LEAD_TIME_CLAUSE_RE.search(text or ""))

    @staticmethod
    def _is_wait_timeout_clause(text: str) -> bool:
        return bool(_WAIT_TIMEOUT_CLAUSE_RE.search(text or ""))

    @staticmethod
    def _purchase_ask(query: str | None) -> bool:
        return bool(_WHO_ASK_RE.search(query or "") and _PURCHASE_ASK_RE.search(query or ""))

    @staticmethod
    def _is_purchase_agency_clause(text: str) -> bool:
        return bool(_PURCHASE_AGENCY_CLAUSE_RE.search(text or ""))

    @staticmethod
    def _is_ds_signing_noise(text: str) -> bool:
        return bool(_DS_SIGNING_NOISE_RE.search(text or ""))

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
        lead_time_ask = self._lead_time_ask(query)
        purchase_ask = self._purchase_ask(query)

        if apply_query_gate and usable:
            ranked = sorted(
                usable,
                key=lambda c: (
                    # WHEN lead-time: prefer initiation/deadline clauses over wait/timeout.
                    (
                        2
                        if lead_time_ask
                        and self._is_lead_time_clause(str(c.get("text") or ""))
                        else (
                            1
                            if when_ask
                            and self._has_temporal_cue(str(c.get("text") or ""))
                            and not (
                                lead_time_ask
                                and self._is_wait_timeout_clause(str(c.get("text") or ""))
                            )
                            else 0
                        )
                    ),
                    # WHO purchase: prefer subcontract/agency over DS/AM signing.
                    (
                        2
                        if purchase_ask
                        and self._is_purchase_agency_clause(str(c.get("text") or ""))
                        else (
                            1
                            if who_ask
                            and self._has_who_agency(str(c.get("text") or ""))
                            and not (
                                purchase_ask
                                and self._is_ds_signing_noise(str(c.get("text") or ""))
                            )
                            else 0
                        )
                    ),
                    self._org_title_boost(query, c),
                    self._rel(query or "", c),
                    float(c.get("score") or 0.0),
                ),
                reverse=True,
            )
            best_rel = self._rel(query or "", ranked[0])
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
                if self._rel(query or "", c)
                >= max(self._min_query_overlap, best_rel * 0.35)
                or float(c.get("score") or 0.0) >= float(ranked[0].get("score") or 0.0)
            ] or ranked
            # Keep only passages that still clear the query-relevance floor.
            usable = [
                c
                for c in usable
                if self._rel(query or "", c) >= self._min_query_overlap
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
            # Lead-time WHEN: if an initiation/deadline clause is in the pool, keep
            # those (and drop wait/timeout neighbors that outrank by raw lex score).
            if lead_time_ask and usable:
                lead_hits = [
                    c
                    for c in usable
                    if self._is_lead_time_clause(str(c.get("text") or ""))
                ]
                if lead_hits:
                    usable = lead_hits
            # Purchase WHO: prefer agency/subcontract clauses when present.
            if purchase_ask and usable:
                purchase_hits = [
                    c
                    for c in usable
                    if self._is_purchase_agency_clause(str(c.get("text") or ""))
                ]
                if purchase_hits:
                    usable = purchase_hits
                else:
                    # Drop DS/AM signing noise when nothing better is available yet —
                    # otherwise escalate rather than answer from amendment clauses.
                    cleaned = [
                        c
                        for c in usable
                        if not self._is_ds_signing_noise(str(c.get("text") or ""))
                    ]
                    if cleaned:
                        usable = cleaned
            # WHEN: do not answer from a weakly topical deadline when a more
            # on-topic hit exists without a number (e.g. SLA п.1.7 vs «3 дня» п.1.5).
            if when_ask and usable and not lead_time_ask:
                temporal = [
                    c
                    for c in usable
                    if self._has_temporal_cue(str(c.get("text") or ""))
                ]
                non_temporal = [c for c in usable if c not in temporal]
                best_temp = max(
                    (self._content_rel(query or "", c) for c in temporal), default=0.0
                )
                best_non_temp = max(
                    (self._content_rel(query or "", c) for c in non_temporal),
                    default=0.0,
                )
                # Topical non-deadline hit (e.g. SLA п.1.7) while numeric neighbor
                # (п.1.5) has near-zero content overlap → escalate (GS-13).
                if (
                    non_temporal
                    and best_non_temp >= self._min_query_overlap
                    and best_temp < self._min_query_overlap
                ):
                    return GroundingResult(
                        ok=False,
                        citations=[],
                        answer_text=None,
                        reason="irrelevant_citations",
                    )
                best_topic = max(
                    (self._rel(query or "", c) for c in usable), default=0.0
                )
                topical_floor = max(self._min_query_overlap, best_topic * 0.5)
                temporal_topical = [
                    c
                    for c in temporal
                    if self._rel(query or "", c) >= topical_floor
                ]
                if temporal_topical:
                    usable = temporal_topical
                elif temporal:
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
                        self._rel(query or "", c)
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
                2.0
                if lead_time_ask and self._is_lead_time_clause(text)
                else 0.0,
                2.0
                if purchase_ask and self._is_purchase_agency_clause(text)
                else 0.0,
                draft_hit,
                1.0 if when_ask and self._has_temporal_cue(text) else 0.0,
                1.0 if who_ask and self._has_who_agency(text) else 0.0,
                self._org_title_boost(query, c),
                self._rel(query or "", c) if apply_query_gate else 0.0,
                float(len(tokenize(text))),
            )

        ordered = sorted(usable, key=_support_key, reverse=True)

        # Try candidates in support order until a short paraphrase grounds.
        last_citations: list[dict[str, Any]] = []
        for top in ordered:
            raw_citations: list[dict[str, Any]] = []
            for c in [top] + [x for x in ordered if x is not top]:
                if len(raw_citations) >= 8:
                    break
                point = normalize_locator(
                    str(c.get("locator") or c.get("section_title") or "")
                )
                raw_citations.append(
                    {
                        "document_id": c["document_id"],
                        "chunk_id": c["chunk_id"],
                        "quote": quote_at_boundary(str(c["text"]), 400),
                        "score": float(c.get("score") or 0.0),
                        "document_title": c.get("document_title"),
                        "locator": point,
                        "source": c.get("source"),
                    }
                )
            # Canonical/learned re-ask: answer form shows one Источник/Цитата —
            # keep a single unique citation when the top hit is learned.
            max_cite = 1 if str(top.get("source") or "") == "learned" else 3
            citations = dedupe_citations(raw_citations, max_n=max_cite)
            # Drop internal source marker from API payload shape.
            citations = [
                {k: v for k, v in cite.items() if k != "source"} for cite in citations
            ]
            last_citations = citations

            title = str(top.get("document_title") or top["document_id"])
            raw_locator = top.get("locator") or top.get("section_title")
            locator = normalize_locator(str(raw_locator) if raw_locator else None)
            quote = str(citations[0].get("quote") or top.get("text") or "")
            chunk_text = str(top.get("text") or "")
            query_rel = self._rel(query or "", top) if apply_query_gate else 1.0
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
