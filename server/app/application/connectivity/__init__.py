"""
ANCHOR: app.application.connectivity
PURPOSE: Dependency connectivity checks for stubs and live adapters.
Dependencies: ports via DI container
"""

from app.application.connectivity.service import ConnectivityService, DependencyStatus

__all__ = ["ConnectivityService", "DependencyStatus"]
