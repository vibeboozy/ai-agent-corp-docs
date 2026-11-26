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

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.config.factories import get_container, reset_container
from app.config.settings import get_settings
from app.logging.setup import RequestIdMiddleware, configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    container = get_container()
    app.state.settings = settings
    app.state.container = container
    yield
    reset_container()


def create_app() -> FastAPI:
    """Build the ASGI app with stub-default DI."""
    settings = get_settings()
    configure_logging(settings)
    app = FastAPI(
        title="Corporate RAG AI-Agent",
        version="0.2.0",
        description=(
            "Corporate RAG AI-Agent API. Default mode uses stubs "
            "(USE_STUBS=true) — no live LLM/Qdrant/Docling/Postgres required."
        ),
        lifespan=lifespan,
    )
    app.add_middleware(
        RequestIdMiddleware,
        header_name=settings.log_correlation_header,
    )
    app.include_router(api_router)
    return app


app = create_app()
