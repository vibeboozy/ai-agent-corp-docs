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
    try:
        # Shared IngestService path: glossary enrich + embed-limit split + upsert.
        result = await container.ingest.ingest_file(
            source_path=src.resolve(),
            document_title=document_title,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 — CLI surface upstream/convert failures
        print(f"error: ingest failed: {exc}", file=sys.stderr)
        return 1
    title = result.get("document_title") or document_title or src.stem
    print(f"ingested {result['chunks']} chunks from {src.name} title={title!r}")
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
