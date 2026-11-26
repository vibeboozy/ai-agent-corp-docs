"""
ANCHOR: app.api.deps
PURPOSE: FastAPI dependency injection for application services and ports.
Dependencies: app.config.factories, application.*
DO:
- Resolve ports via factories from Settings
DONT:
- Construct Http*/Qdrant*/SqlAlchemy* inside routers ad hoc
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from app.config.factories import Container, get_container
from app.config.settings import Settings, get_settings
from app.domain.errors import ForbiddenError, UnauthorizedError


def get_app_container() -> Container:
    return get_container()


SettingsDep = Annotated[Settings, Depends(get_settings)]
ContainerDep = Annotated[Container, Depends(get_app_container)]


async def require_user_headers(
    settings: SettingsDep,
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
) -> str | None:
    if settings.auth_mode == "none":
        return x_user_id
    if settings.auth_mode == "header":
        if not x_user_id:
            raise UnauthorizedError("X-User-Id required")
        return x_user_id
    return x_user_id


async def require_officer(
    settings: SettingsDep,
    x_officer_token: Annotated[str | None, Header(alias="X-Officer-Token")] = None,
) -> None:
    if settings.auth_mode == "none":
        return
    if settings.auth_mode == "header":
        expected = settings.auth_officer_token
        if not expected or x_officer_token != expected:
            raise ForbiddenError("Officer token required")


def http_error(exc: Exception) -> HTTPException:
    from app.domain.errors import (
        AppError,
        ConflictError,
        ForbiddenError,
        NotFoundError,
        UnauthorizedError,
        UpstreamTimeoutError,
    )

    if isinstance(exc, NotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": exc.detail, "code": exc.code},
        )
    if isinstance(exc, ConflictError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"detail": exc.detail, "code": exc.code},
        )
    if isinstance(exc, UnauthorizedError):
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"detail": exc.detail, "code": exc.code},
        )
    if isinstance(exc, ForbiddenError):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"detail": exc.detail, "code": exc.code},
        )
    if isinstance(exc, UpstreamTimeoutError):
        return HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={"detail": exc.detail, "code": exc.code},
        )
    if isinstance(exc, AppError):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"detail": exc.detail, "code": exc.code},
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={"detail": "Internal error", "code": "INTERNAL_ERROR"},
    )
