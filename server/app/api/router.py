"""
ANCHOR: app.api.router
PURPOSE: Aggregate API routers under configurable API_PREFIX (default /api/v1).
Dependencies: app.api.appeals, app.api.stats, app.api.health
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api import appeals, health, stats


def build_api_router(*, api_prefix: str = "/api/v1") -> APIRouter:
    """Mount health (dual paths) + versioned appeals/stats under api_prefix."""
    prefix = api_prefix.rstrip("/") or "/api/v1"
    root = APIRouter()
    root.include_router(health.router)
    root.include_router(appeals.router, prefix=prefix)
    root.include_router(stats.router, prefix=prefix)
    return root


# Default router for import compatibility (tests / OpenAPI smoke).
api_router = build_api_router()
