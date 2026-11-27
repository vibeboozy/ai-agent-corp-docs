"""
ANCHOR: app.main
PURPOSE: FastAPI ASGI entrypoint; mounts /api/v1 routers and health.
Dependencies: app.api, app.config, app.logging
CRITICAL: Always wires real LLM/Qdrant/Docling/Postgres adapters from Settings.
DO:
- Expose OpenAPI for documented REST paths
- Wire DI factories from Settings
DONT:
- Implement RAG or persistence logic here
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.api.router import build_api_router
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
    """Build the ASGI app with real-adapter DI."""
    settings = get_settings()
    configure_logging(settings)
    app = FastAPI(
        title="Corporate RAG AI-Agent",
        version="0.3.0",
        description=(
            "Corporate RAG AI-Agent API. Uses LLM, embeddings, "
            "Qdrant, Docling, and Postgres clients configured via environment."
        ),
        debug=settings.app_env.lower() in {"development", "dev", "local"},
        lifespan=lifespan,
    )
    app.add_middleware(
        RequestIdMiddleware,
        header_name=settings.log_correlation_header,
        log_request_body=settings.log_request_body,
        log_redact_secrets=settings.log_redact_secrets,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(build_api_router(api_prefix=settings.api_prefix))
    return app


app = create_app()
