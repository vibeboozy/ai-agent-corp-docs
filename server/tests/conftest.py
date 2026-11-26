"""
ANCHOR: tests.conftest
PURPOSE: Shared pytest fixtures (ASGI client + DI cache resets + live readiness).
Dependencies: app.main, app.config.factories
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.config.factories import reset_container
from app.config.settings import clear_settings_cache
from app.main import create_app


@pytest.fixture(autouse=True)
def _reset_di() -> None:
    clear_settings_cache()
    reset_container()
    yield
    clear_settings_cache()
    reset_container()


@pytest.fixture
def client() -> TestClient:
    with TestClient(create_app()) as c:
        yield c


def _run_coro(coro: object) -> object:
    """Run a coroutine from sync or already-async pytest contexts."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)  # type: ignore[arg-type]
    # Inside pytest-asyncio: asyncio.run is forbidden — use a fresh thread/loop.
    import concurrent.futures

    def _in_thread() -> object:
        return asyncio.run(coro)  # type: ignore[arg-type]

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(_in_thread).result(timeout=60)


def _ping_named(container: object, name: str) -> bool:
    """Map logical service name → container port ping."""
    mapping = {
        "llm": "llm",
        "embeddings": "embeddings",
        "qdrant": "vectorstore",
        "docling": "docling",
        "postgres": "persistence",
    }
    attr = mapping.get(name)
    if not attr:
        return False
    port = getattr(container, attr, None)
    if port is None:
        return False

    async def _run() -> bool:
        return bool(await port.ping())

    try:
        return bool(_run_coro(_run()))
    except Exception:
        return False


def services_available(*names: str) -> bool:
    """
    True when every named dependency answers ping via normal Settings config.

    Live/integration tests run when infra is up, and skip cleanly when it is not.
    """
    if not names:
        return False
    try:
        from app.config.factories import build_container
        from app.config.settings import Settings, clear_settings_cache

        clear_settings_cache()
        container = build_container(Settings())
        return all(_ping_named(container, n) for n in names)
    except Exception:
        return False


def require_services(*names: str) -> None:
    """pytest.skip unless all named services are reachable."""
    missing: list[str] = []
    for name in names:
        if not services_available(name):
            missing.append(name)
    if missing:
        pytest.skip(f"services not available: {', '.join(missing)}")


def require_all_core_services() -> None:
    require_services("llm", "embeddings", "qdrant", "docling", "postgres")
