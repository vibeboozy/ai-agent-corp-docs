"""
ANCHOR: app.logging.setup
PURPOSE: Configure process logging from Settings (JSON + request_id middleware).
Dependencies: logging, app.config.settings
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config.settings import Settings


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("request_id", "appeal_id", "path", "method", "status_code", "latency_ms"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(settings: Settings) -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler()
    if settings.log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
    root.addHandler(handler)
    root.setLevel(level)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Echo/set X-Request-Id and log request outcomes."""

    def __init__(self, app, *, header_name: str = "X-Request-Id") -> None:  # noqa: ANN001
        super().__init__(app)
        self._header = header_name
        self._log = logging.getLogger("app.request")

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get(self._header) or str(uuid.uuid4())
        request.state.request_id = request_id
        started = time.perf_counter()
        response = await call_next(request)
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        response.headers[self._header] = request_id
        self._log.info(
            "request",
            extra={
                "request_id": request_id,
                "path": request.url.path,
                "method": request.method,
                "status_code": response.status_code,
                "latency_ms": latency_ms,
            },
        )
        return response
