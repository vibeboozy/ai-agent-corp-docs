"""
ANCHOR: app.api.deps
PURPOSE: FastAPI dependency injection placeholders for application services and ports.
Dependencies: app.config.factories, application.*
DO:
- Resolve ports via factories from Settings
DONT:
- Construct Stub*/Http* inside routers ad hoc
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.config.factories import build_container
from app.config.settings import Settings, get_settings


def get_container(settings: Annotated[Settings, Depends(get_settings)]):
    """Return a DI container skeleton (ports selected by env)."""
    return build_container(settings)
