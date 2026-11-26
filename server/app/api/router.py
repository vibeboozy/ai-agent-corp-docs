"""
ANCHOR: app.api.router
PURPOSE: Aggregate API routers under /api/v1.
Dependencies: app.api.appeals, app.api.stats, app.api.health
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api import appeals, health, stats

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(appeals.router, prefix="/api/v1")
api_router.include_router(stats.router, prefix="/api/v1")
