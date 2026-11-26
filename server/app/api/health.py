"""
ANCHOR: app.api.health
PURPOSE: Liveness/readiness stub for process health (not RAG readiness).
Dependencies: none
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
