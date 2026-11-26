"""
ANCHOR: app.main
PURPOSE: FastAPI ASGI entrypoint; mounts /api/v1 routers and health.
Dependencies: app.api, app.config, app.logging
CRITICAL: Default USE_STUBS=true — no outbound LLM/Qdrant/Docling on boot (ANC-STUB-01).
DO:
- Expose OpenAPI for documented REST paths
- Wire DI factories from Settings
DONT:
- Implement RAG or persistence logic here
- Call live providers from lifespan without flags
"""

from __future__ import annotations

from fastapi import FastAPI

from app.api.router import api_router
from app.config.settings import get_settings
from app.logging.setup import configure_logging


def create_app() -> FastAPI:
    """Build the ASGI app. Handlers remain stubs until later phases."""
    settings = get_settings()
    configure_logging(settings)
    app = FastAPI(
        title="Corporate RAG AI-Agent",
        version="0.1.0",
        description="Skeleton only — stubs/NotImplemented; no real RAG/DB wiring.",
    )
    app.include_router(api_router)
    return app


app = create_app()
