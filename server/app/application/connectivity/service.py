"""
ANCHOR: app.application.connectivity.service
PURPOSE: Probe LLM/embeddings/Qdrant/Docling/Postgres health (stub or live).
Dependencies: adapter ports via Container; Settings stub flags
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
    mode: str  # stub | live
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


async def _safe_ping(
    name: str,
    *,
    mode: str,
    ping: Callable[[], Awaitable[bool]],
) -> DependencyStatus:
    try:
        ok = bool(await ping())
        return DependencyStatus(
            name=name,
            ok=ok,
            mode=mode,
            detail=None if ok else "ping returned false",
        )
    except Exception as exc:  # noqa: BLE001 — surface adapter failures as status
        return DependencyStatus(
            name=name,
            ok=False,
            mode=mode,
            detail=type(exc).__name__,
        )


class ConnectivityService:
    """Run connectivity probes against DI-selected adapters."""

    def __init__(
        self,
        *,
        llm: Any,
        embeddings: Any,
        vectorstore: Any,
        docling: Any,
        persistence: Any,
        stub_flags: dict[str, bool],
    ) -> None:
        self._llm = llm
        self._embeddings = embeddings
        self._vectorstore = vectorstore
        self._docling = docling
        self._persistence = persistence
        self._stub_flags = stub_flags

    def _mode(self, key: str) -> str:
        return "stub" if self._stub_flags.get(key, True) else "live"

    async def check_all(self) -> list[DependencyStatus]:
        return [
            await _safe_ping("llm", mode=self._mode("llm"), ping=self._llm.ping),
            await _safe_ping(
                "embeddings", mode=self._mode("embeddings"), ping=self._embeddings.ping
            ),
            await _safe_ping(
                "qdrant", mode=self._mode("vectorstore"), ping=self._vectorstore.ping
            ),
            await _safe_ping("docling", mode=self._mode("docling"), ping=self._docling.ping),
            await _safe_ping(
                "postgres", mode=self._mode("persistence"), ping=self._persistence.ping
            ),
        ]

    async def check_report(self) -> dict[str, Any]:
        results = await self.check_all()
        overall = "ok" if all(r.ok for r in results) else "degraded"
        return {
            "status": overall,
            "dependencies": [r.to_dict() for r in results],
        }
