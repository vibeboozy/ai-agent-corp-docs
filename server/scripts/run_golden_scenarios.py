#!/usr/bin/env python3
"""
ANCHOR: scripts.run_golden_scenarios
PURPOSE: Local live golden-set runner — read-only dialogue vs .env stack; paste log.
Dependencies: scenarios/golden-set.yaml; LangGraph dialogue (no Postgres/Qdrant writes)

From server/ (with .env + ingested corpus):

    python scripts/run_golden_scenarios.py

Writes ``artifacts/golden-run.log`` (override with ``--out``). Paste that file back.
Does **not** upsert Qdrant or create quality appeals — graph only.
Requires PyYAML (``pip install pyyaml`` if missing).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# server/ on sys.path when invoked as ``python scripts/run_golden_scenarios.py``
_SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVER_ROOT))

_DEFAULT_SCENARIOS = _SERVER_ROOT / "scenarios" / "golden-set.yaml"
_DEFAULT_OUT = _SERVER_ROOT / "artifacts" / "golden-run.log"

_STATUS_MAP = {
    "answer": "answered",
    "clarify": "clarifying",
    "escalate": "escalated",
    "refuse": "refused",
}


def _load_cases(path: Path) -> list[dict[str, Any]]:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "PyYAML required: pip install pyyaml\n"
            f"({exc})"
        ) from exc
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    cases = list((data or {}).get("cases") or [])
    if not cases:
        raise SystemExit(f"no cases in {path}")
    return cases


def _build_live_graph() -> tuple[Any, Any]:
    """Live LLM + retrieval + grounding; no persistence / Qdrant writes."""
    from app.application.dialogue.graph import build_dialogue_graph
    from app.application.dialogue.nodes import DialogueDeps
    from app.application.grounding.service import GroundingService
    from app.application.retrieval.service import RetrievalService
    from app.config import factories as factories_mod
    from app.config.settings import Settings, clear_settings_cache
    from app.domain.glossary import build_glossary

    clear_settings_cache()
    settings = Settings()
    llm = factories_mod._build_llm(settings)
    embeddings = factories_mod._build_embeddings(settings)
    vectorstore = factories_mod._build_vectorstore(settings)
    build_glossary.cache_clear()
    glossary = build_glossary(
        glossary_text=settings.abbreviation_glossary or "",
        glossary_path=settings.abbreviation_glossary_path or "",
        expand_query=settings.abbreviation_expand_query,
        enrich_ingest=settings.abbreviation_enrich_ingest,
        use_defaults=settings.abbreviation_use_defaults,
    )
    retrieval = RetrievalService(
        embeddings=embeddings,
        vectorstore=vectorstore,
        prefetch=settings.retrieval_prefetch,
        prefer_latest=settings.retrieval_prefer_latest,
        rerank_mode=settings.rerank_mode,
        rerank_candidates=settings.rerank_candidates,
        rerank_top_k=settings.rerank_top_k,
        rerank_max_per_doc=settings.rerank_max_per_doc,
        rerank_min_score=settings.rerank_min_score,
        llm=llm,
        rerank_llm_model=settings.rerank_llm_model,
        glossary=glossary,
        lexical_weight=settings.retrieval_lexical_weight,
    )
    grounding = GroundingService(
        min_citations=settings.grounding_min_citations,
        min_score=settings.grounding_min_score,
        min_query_overlap=settings.grounding_min_query_overlap,
        glossary=glossary,
    )
    deps = DialogueDeps(
        llm=llm,
        retrieval=retrieval,
        grounding=grounding,
        quality_email=settings.quality_service_email,
        allowed_topics=settings.resolved_allowed_topics(),
    )
    return build_dialogue_graph(deps), settings


def _format_case_block(
    case: dict[str, Any],
    *,
    out: dict[str, Any],
    settings: Any,
    error: str | None = None,
) -> str:
    cid = case.get("id", "?")
    expected = case.get("scenario", "?")
    if error:
        return "\n".join(
            [
                f"### GOLDEN LOG · {cid} · expected={expected} · actual=ERROR",
                f"- **question:** {case.get('question')}",
                f"- **expected_behavior:** {case.get('expected_behavior')}",
                f"- **expected_doc / locator:** {case.get('expected_doc') or '—'} / "
                f"{case.get('locator') or '—'}",
                "- **log (paste back):**",
                "  - status: error",
                f"  - summary/answer: {error!r}",
                "  - citations (doc, locator, score):",
                "    - (none)",
                "  - escalation reason: —",
                "  - gates: {}",
                "",
            ]
        )

    outcome = str(out.get("outcome") or "")
    status = _STATUS_MAP.get(outcome, outcome or "?")
    match = "MATCH" if outcome == expected else "MISMATCH"
    answer = out.get("draft_answer") or out.get("clarification_text") or ""
    citations = list(out.get("citations") or [])
    cite_lines: list[str] = []
    for c in citations:
        quote = str(c.get("quote") or "")
        if len(quote) > 160:
            quote = quote[:157] + "…"
        cite_lines.append(
            "    - doc={doc!r} locator={loc!r} score={score} chunk_id={cid!r}\n"
            "      quote: {quote}".format(
                doc=c.get("document_title") or c.get("document_id"),
                loc=c.get("locator"),
                score=c.get("score"),
                cid=c.get("chunk_id"),
                quote=quote,
            )
        )
    if not cite_lines:
        cite_lines = ["    - (none)"]

    candidates = list(out.get("candidates") or [])
    cand_brief = []
    for c in candidates[:5]:
        cand_brief.append(
            {
                "chunk_id": c.get("chunk_id"),
                "score": c.get("score"),
                "lexical_score": c.get("lexical_score"),
                "vector_score": c.get("vector_score"),
                "locator": c.get("locator") or c.get("section_title"),
                "title": c.get("document_title"),
                "text_preview": str(c.get("text") or "")[:120],
            }
        )

    gates: dict[str, Any] = {
        "specificity": out.get("specificity"),
        "raw_specificity": out.get("raw_specificity"),
        "grounded": out.get("grounded"),
        "escalation_reason": out.get("escalation_reason"),
        "clarify_reason": out.get("clarify_reason"),
        "node_trace": list(out.get("node_trace") or []),
        "rerank_mode": out.get("rerank_mode"),
        "hit_count": len(candidates),
        "grounding_min_score": getattr(settings, "grounding_min_score", None),
        "grounding_min_query_overlap": getattr(
            settings, "grounding_min_query_overlap", None
        ),
        "top_candidates": cand_brief,
    }
    trace = " ".join(str(t) for t in gates["node_trace"])
    if "paraphrase_required" in trace:
        gates["gate_hint"] = "paraphrase_required"
    elif "irrelevant_citations" in trace:
        gates["gate_hint"] = "irrelevant_citations"
    elif "insufficient_citations" in trace:
        gates["gate_hint"] = "insufficient_citations"

    answer_preview = str(answer).strip()
    if len(answer_preview) > 600:
        answer_preview = answer_preview[:597] + "…"

    return "\n".join(
        [
            f"### GOLDEN LOG · {cid} · expected={expected} · actual={outcome} · {match}",
            f"- **question:** {case.get('question')}",
            f"- **expected_behavior:** {case.get('expected_behavior')}",
            f"- **expected_doc / locator:** {case.get('expected_doc') or '—'} / "
            f"{case.get('locator') or '—'}",
            "- **log (paste back):**",
            f"  - status: {status}",
            f"  - summary/answer: {answer_preview!r}",
            "  - citations (doc, locator, score):",
            *cite_lines,
            f"  - escalation reason: {out.get('escalation_reason') or '—'}",
            f"  - gates: ```json\n{json.dumps(gates, ensure_ascii=False, indent=2)}\n```",
            "",
        ]
    )


async def _run_one(graph: Any, settings: Any, case: dict[str, Any]) -> dict[str, Any]:
    return await graph.ainvoke(
        {
            "user_message": case["question"],
            "history": [],
            "clarify_turns": 0,
            "max_clarify_turns": int(
                getattr(settings, "dialogue_max_clarify_turns", 3) or 3
            ),
            "node_trace": [],
        }
    )


async def _main_async(args: argparse.Namespace) -> int:
    scenarios_path = Path(args.scenarios).resolve()
    out_path = Path(args.out).resolve()
    cases = _load_cases(scenarios_path)
    if args.only:
        want = {x.strip() for x in args.only.split(",") if x.strip()}
        cases = [c for c in cases if c.get("id") in want]
        if not cases:
            print(f"no cases matched --only {args.only!r}", file=sys.stderr)
            return 2

    print(f"scenarios: {scenarios_path}", flush=True)
    print(f"cases: {len(cases)}", flush=True)
    print("building live graph (llm + embeddings + qdrant, read-only)…", flush=True)
    try:
        graph, settings = _build_live_graph()
    except Exception as exc:
        print(f"failed to wire live stack: {exc}", file=sys.stderr)
        return 1

    started = datetime.now(timezone.utc).isoformat()
    blocks: list[str] = [
        "# Golden scenario run (paste-friendly)",
        f"- started_utc: {started}",
        f"- scenarios: {scenarios_path}",
        f"- cases: {len(cases)}",
        "- mode: read-only LangGraph (no Qdrant upsert / no Postgres appeals)",
        "",
    ]
    matches = 0
    errors = 0
    for i, case in enumerate(cases, 1):
        cid = case.get("id", f"#{i}")
        print(f"[{i}/{len(cases)}] {cid} …", flush=True)
        try:
            out = await _run_one(graph, settings, case)
            block = _format_case_block(case, out=out, settings=settings)
            if str(out.get("outcome") or "") == case.get("scenario"):
                matches += 1
        except Exception as exc:
            errors += 1
            block = _format_case_block(
                case, out={}, settings=settings, error=f"{type(exc).__name__}: {exc}"
            )
        blocks.append(block)
        # Stream progress line to stdout; full detail goes to the log file.
        first = block.splitlines()[0] if block else cid
        print(f"  {first}", flush=True)

    finished = datetime.now(timezone.utc).isoformat()
    summary = (
        f"# Summary: match={matches}/{len(cases)} errors={errors} "
        f"finished_utc={finished}"
    )
    blocks.append(summary)
    blocks.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(blocks)
    out_path.write_text(text, encoding="utf-8")
    print(summary, flush=True)
    print(f"wrote: {out_path}", flush=True)
    print("(paste that log file back)", flush=True)
    return 0 if errors == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run golden scenarios against live dialogue; write paste log."
    )
    parser.add_argument(
        "--scenarios",
        type=Path,
        default=_DEFAULT_SCENARIOS,
        help=f"YAML scenarios (default: {_DEFAULT_SCENARIOS})",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=_DEFAULT_OUT,
        help=f"Output log path (default: {_DEFAULT_OUT})",
    )
    parser.add_argument(
        "--only",
        default="",
        help="Comma-separated case ids (e.g. GS-01,GS-02)",
    )
    return asyncio.run(_main_async(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
