"""Configuration Manager — loads, validates, and persists JARMINEI's typed AppConfig.

Usage:
    from config import load_config
    config = load_config()
"""

from config.errors import ConfigError
from config.loader import ConfigLoader, load_config
from config.schema import (
    VALID_LOG_LEVELS,
    AppConfig,
    DatabaseConfig,
    LoggingConfig,
    ModelConfig,
    ResourceThresholds,
    UIConfig,
    VoiceConfig,
)

__all__ = [
    "VALID_LOG_LEVELS",
    "AppConfig",
    "ConfigError",
    "ConfigLoader",
    "DatabaseConfig",
    "LoggingConfig",
    "ModelConfig",
    "ResourceThresholds",
    "UIConfig",
    "VoiceConfig",
    "load_config",
]
