"""Core Manager — orchestration, startup/shutdown, module registration, health monitoring.

Usage:
    from core import get_logger
    logger = get_logger(__name__)
"""

from core.logging_setup import configure_logging, get_logger

__all__ = [
    "configure_logging",
    "get_logger",
]
