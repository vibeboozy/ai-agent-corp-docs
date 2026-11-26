"""
ANCHOR: app.api.health
PURPOSE: Liveness plus optional dependency connectivity report.
Dependencies: app.api.deps / connectivity service
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import ContainerDep

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/api/v1/health")
async def health_v1() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/dependencies")
@router.get("/api/v1/health/dependencies")
async def health_dependencies(container: ContainerDep) -> dict:
    """Per-adapter connectivity (stub or live). Does not gate process liveness."""
    return await container.connectivity.check_report()
