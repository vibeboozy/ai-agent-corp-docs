"""
ANCHOR: app.application.connectivity.service
PURPOSE: Probe LLM/embeddings/Qdrant/Docling/Postgres health.
Dependencies: adapter ports via Container
DO:
- Report per-service ok/fail without leaking secrets
DONT:
- Fail the process health endpoint on optional upstream outages alone
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Awaitable, Callable


@dataclass
class DependencyStatus:
    name: str
    ok: bool
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


async def _safe_ping(
    name: str,
    *,
    ping: Callable[[], Awaitable[bool]],
) -> DependencyStatus:
    try:
        ok = bool(await ping())
        return DependencyStatus(
            name=name,
            ok=ok,
            detail=None if ok else "ping returned false",
        )
    except Exception as exc:  # noqa: BLE001 — surface adapter failures as status
        return DependencyStatus(
            name=name,
            ok=False,
            detail=type(exc).__name__,
        )


class ConnectivityService:
    """Run connectivity probes against DI-wired adapters."""

    def __init__(
        self,
        *,
        llm: Any,
        embeddings: Any,
        vectorstore: Any,
        docling: Any,
        persistence: Any,
    ) -> None:
        self._llm = llm
        self._embeddings = embeddings
        self._vectorstore = vectorstore
        self._docling = docling
        self._persistence = persistence

    async def check_all(self) -> list[DependencyStatus]:
        return [
            await _safe_ping("llm", ping=self._llm.ping),
            await _safe_ping("embeddings", ping=self._embeddings.ping),
            await _safe_ping("qdrant", ping=self._vectorstore.ping),
            await _safe_ping("docling", ping=self._docling.ping),
            await _safe_ping("postgres", ping=self._persistence.ping),
        ]

    async def check_report(self) -> dict[str, Any]:
        results = await self.check_all()
        overall = "ok" if all(r.ok for r in results) else "degraded"
        return {
            "status": overall,
            "dependencies": [r.to_dict() for r in results],
        }
