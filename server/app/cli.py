"""
ANCHOR: app.cli
PURPOSE: CLI entrypoints — connectivity `check` and helpers.
Dependencies: app.config.factories, connectivity service
DO:
- Print per-dependency ok/fail without secrets
DONT:
- Require live infra when USE_STUBS=true
"""

from __future__ import annotations

import argparse
import asyncio
import sys


def _print_report(report: dict) -> int:
    status = report.get("status", "unknown")
    print(f"overall: {status}")
    for dep in report.get("dependencies") or []:
        mark = "OK" if dep.get("ok") else "FAIL"
        detail = f" ({dep['detail']})" if dep.get("detail") else ""
        print(f"  [{mark}] {dep.get('name')} mode={dep.get('mode')}{detail}")
    return 0 if status == "ok" else 1


async def _run_check() -> int:
    from app.config.factories import build_container
    from app.config.settings import clear_settings_cache, get_settings

    clear_settings_cache()
    settings = get_settings()
    container = build_container(settings)
    report = await container.connectivity.check_report()
    return _print_report(report)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rag-server", description="Corporate RAG server CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    check_p = sub.add_parser("check", help="Probe LLM/embeddings/Qdrant/Docling/Postgres")
    check_p.set_defaults(_handler="check")

    args = parser.parse_args(argv)
    if args.command == "check":
        return asyncio.run(_run_check())
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
