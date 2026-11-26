"""
ANCHOR: app.logging.setup
PURPOSE: Configure process logging from Settings (skeleton).
Dependencies: logging, app.config.settings
"""

from __future__ import annotations

import logging

from app.config.settings import Settings


def configure_logging(settings: Settings) -> None:
    """Minimal logging configuration — JSON/redaction added later."""
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(level=level, format="%(levelname)s %(name)s %(message)s")
