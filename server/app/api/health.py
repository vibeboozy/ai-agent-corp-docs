"""
ANCHOR: app.api.health
PURPOSE: Liveness/readiness for process health (not RAG readiness).
Dependencies: none
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/api/v1/health")
async def health_v1() -> dict[str, str]:
    return {"status": "ok"}
