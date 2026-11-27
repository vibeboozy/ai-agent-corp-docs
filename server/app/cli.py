"""
ANCHOR: app.cli
PURPOSE: CLI entrypoints — connectivity `check`, Docling file ingest helper.
Dependencies: app.config.factories, connectivity service, ingest
DO:
- Print per-dependency ok/fail without secrets
- Expose via console_scripts `rag-server` and `python -m app.cli`
DONT:
- Hide dependency failures (always probes real adapters)
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Primary subcommand: ingest-file. Cheap aliases for older/shorter names.
_INGEST_COMMANDS = frozenset({"ingest-file", "ingest", "ingest-docx"})


def _print_report(report: dict) -> int:
    status = report.get("status", "unknown")
    print(f"overall: {status}")
    for dep in report.get("dependencies") or []:
        mark = "OK" if dep.get("ok") else "FAIL"
        detail = f" ({dep['detail']})" if dep.get("detail") else ""
        print(f"  [{mark}] {dep.get('name')}{detail}")
    return 0 if status == "ok" else 1


async def _run_check() -> int:
    from app.config.factories import build_container
    from app.config.settings import clear_settings_cache, get_settings

    clear_settings_cache()
    settings = get_settings()
    container = build_container(settings)
    report = await container.connectivity.check_report()
    return _print_report(report)


async def _run_ingest(path: str, *, document_title: str | None) -> int:
    """Convert a local Docling-supported file (docx/pdf/…) and upsert chunks."""
    from app.config.factories import build_container
    from app.config.settings import clear_settings_cache, get_settings

    clear_settings_cache()
    settings = get_settings()
    container = build_container(settings)
    src = Path(path)
    if not src.is_file():
        # Resolve relative paths against DOCS_CORPUS_PATH / DOCS_DIR when needed.
        corpus = Path(settings.resolved_docs_corpus_path())
        candidate = corpus / path
        if candidate.is_file():
            src = candidate
        else:
            print(
                f"error: file not found: {path} "
                f"(also checked under corpus {corpus})",
                file=sys.stderr,
            )
            return 2
    converted = await container.docling.convert(source_path=str(src.resolve()))
    chunks = converted.get("chunks") or []
    if not chunks:
        print("error: Docling returned no chunks", file=sys.stderr)
        return 1
    title = document_title or src.stem
    glossary = getattr(container, "glossary", None)
    # Expand abbreviations into chunk TEXT before embed (dense + sparse).
    enriched = []
    for chunk in chunks:
        body = str(chunk.get("text") or "")
        if glossary is not None:
            body = glossary.enrich_text(body)
        enriched.append({**chunk, "text": body})
    texts = [c["text"] for c in enriched]
    vectors = await container.embeddings.embed_dense(texts)
    sparse_maps = await container.embeddings.embed_sparse(texts)
    upserts = []
    for idx, chunk in enumerate(enriched):
        meta: dict = {"source_path": str(src)}
        if chunk.get("section_title"):
            meta["section_title"] = chunk["section_title"]
        if glossary is not None:
            meta = glossary.enrich_metadata(str(chunk["text"]), meta)
        upserts.append(
            {
                "document_id": f"doc-{src.stem}",
                "chunk_id": chunk.get("chunk_id") or f"c-{idx}",
                "text": chunk["text"],
                "document_title": title,
                "source": "ingest",
                "locator": chunk.get("locator") or chunk.get("section_title"),
                "dense_vector": vectors[idx] if idx < len(vectors) else None,
                "sparse_vector": sparse_maps[idx] if idx < len(sparse_maps) else None,
                "metadata": meta,
            }
        )
    await container.vectorstore.upsert(upserts)
    print(f"ingested {len(upserts)} chunks from {src.name} title={title!r}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rag-server", description="Corporate RAG server CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="Probe LLM/embeddings/Qdrant/Docling/Postgres")

    ingest_p = sub.add_parser(
        "ingest-file",
        aliases=["ingest", "ingest-docx"],
        help=(
            "Ingest a local Docling-supported file (docx/pdf/…) via "
            "Docling Serve /v1/convert/source (base64 FileSource)"
        ),
    )
    ingest_p.add_argument(
        "path",
        help="Path to a Docling-supported file (.docx, .pdf, …)",
    )
    ingest_p.add_argument("--title", default=None, help="Document title override")

    args = parser.parse_args(argv)
    if args.command == "check":
        return asyncio.run(_run_check())
    if args.command in _INGEST_COMMANDS:
        return asyncio.run(_run_ingest(args.path, document_title=args.title))
    parser.error(f"unknown command: {args.command}")
    return 2


def run() -> None:
    """console_scripts entry — always exit with the command status code."""
    raise SystemExit(main())


if __name__ == "__main__":
    run()
