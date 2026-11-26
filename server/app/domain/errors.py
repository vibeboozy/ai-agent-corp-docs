"""
ANCHOR: app.domain.errors
PURPOSE: Typed domain/application errors mapped to HTTP codes in the API layer.
Dependencies: none
DO:
- Prefer typed errors over bare Exception for business outcomes
DONT:
- Leak secrets in error messages
"""

from __future__ import annotations


class AppError(Exception):
    """Base application error with stable machine code."""

    def __init__(self, detail: str, *, code: str) -> None:
        super().__init__(detail)
        self.detail = detail
        self.code = code


class NotFoundError(AppError):
    def __init__(self, detail: str = "Resource not found") -> None:
        super().__init__(detail, code="NOT_FOUND")


class ConflictError(AppError):
    def __init__(self, detail: str, *, code: str = "CONFLICT_STATUS") -> None:
        super().__init__(detail, code=code)


class UnauthorizedError(AppError):
    def __init__(self, detail: str = "Unauthorized") -> None:
        super().__init__(detail, code="UNAUTHORIZED")


class ForbiddenError(AppError):
    def __init__(self, detail: str = "Forbidden") -> None:
        super().__init__(detail, code="FORBIDDEN")


class UpstreamTimeoutError(AppError):
    def __init__(self, detail: str = "Upstream timeout") -> None:
        super().__init__(detail, code="UPSTREAM_TIMEOUT")
