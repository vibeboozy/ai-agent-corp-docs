"""
ANCHOR: app.api.stats
PURPOSE: Aggregate stats endpoint stub (reads persistence in later phases).
Dependencies: application / persistence port
DONT:
- Compute stats from process memory alone in production path
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.schemas import StatsResponse

router = APIRouter(tags=["stats"])


@router.get("/stats", response_model=StatsResponse)
async def get_stats() -> StatsResponse:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"detail": "Stats not implemented", "code": "NOT_IMPLEMENTED"},
    )
