"""
ANCHOR: app.api.stats
PURPOSE: Aggregate stats endpoint reading persistence.
Dependencies: application / persistence port
DONT:
- Compute stats from process memory alone in production path
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import ContainerDep, http_error
from app.api.schemas import StatsResponse, StatsWindow
from app.domain.errors import AppError

router = APIRouter(tags=["stats"])


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    container: ContainerDep,
    from_time: Annotated[datetime | None, Query(alias="from")] = None,
    to: datetime | None = None,
) -> StatsResponse:
    try:
        raw = await container.persistence.get_stats(created_from=from_time, created_to=to)
    except AppError as exc:
        raise http_error(exc) from exc
    window = raw.get("window") or {}
    return StatsResponse(
        appeals_total=raw.get("appeals_total", 0),
        by_status=raw.get("by_status") or {},
        messages_total=raw.get("messages_total", 0),
        clarify_rate=float(raw.get("clarify_rate") or 0.0),
        escalation_rate=float(raw.get("escalation_rate") or 0.0),
        answered_rate=float(raw.get("answered_rate") or 0.0),
        learning_updates=int(raw.get("learning_updates") or 0),
        window=StatsWindow.model_validate(
            {"from": window.get("from"), "to": window.get("to")}
        ),
    )
