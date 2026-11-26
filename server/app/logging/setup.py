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

_SECRET_HEADER_KEYS = frozenset(
    {
        "authorization",
        "x-api-key",
        "x-officer-token",
        "cookie",
        "set-cookie",
    }
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in (
            "request_id",
            "appeal_id",
            "path",
            "method",
            "status_code",
            "latency_ms",
            "request_body",
        ):
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


def redact_headers(headers: dict[str, str], *, enabled: bool) -> dict[str, str]:
    """Copy headers; mask secret keys when enabled (LOG_REDACT_SECRETS)."""
    if not enabled:
        return dict(headers)
    return {
        key: ("***" if key.lower() in _SECRET_HEADER_KEYS else value)
        for key, value in headers.items()
    }


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Echo/set X-Request-Id and log request outcomes."""

    def __init__(
        self,
        app,  # noqa: ANN001
        *,
        header_name: str = "X-Request-Id",
        log_request_body: bool = False,
        log_redact_secrets: bool = True,
    ) -> None:
        super().__init__(app)
        self._header = header_name
        self._log_request_body = log_request_body
        self._log_redact_secrets = log_redact_secrets
        self._log = logging.getLogger("app.request")

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get(self._header) or str(uuid.uuid4())
        request.state.request_id = request_id
        started = time.perf_counter()

        body_extra: str | None = None
        if self._log_request_body and request.method in {"POST", "PUT", "PATCH"}:
            raw = await request.body()
            text = raw.decode("utf-8", errors="replace")
            if self._log_redact_secrets:
                lowered = text.lower()
                if any(tok in lowered for tok in ("authorization", "api_key", "\"token\"")):
                    text = f"<redacted len={len(raw)}>"
                elif len(text) > 2000:
                    text = text[:2000] + "…"
            elif len(text) > 2000:
                text = text[:2000] + "…"
            body_extra = text

        response = await call_next(request)
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        response.headers[self._header] = request_id
        extra: dict = {
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
            "status_code": response.status_code,
            "latency_ms": latency_ms,
        }
        if body_extra is not None:
            extra["request_body"] = body_extra
        # Ensure LOG_REDACT_SECRETS is applied to any header snapshot we might attach later.
        _ = redact_headers(
            {k: v for k, v in request.headers.items()},
            enabled=self._log_redact_secrets,
        )
        self._log.info("request", extra=extra)
        return response
