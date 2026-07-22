"""Load, validate, and persist JARMINEI's configuration.

Precedence (lowest to highest): defaults.yaml -> local.yaml (optional,
gitignored, machine-specific) -> JARMINEI_<SECTION>_<FIELD> environment
variables. See docs/sprint_book/sprint_1_2.md for the design rationale.
"""

import os
import typing
from dataclasses import asdict
from pathlib import Path
from typing import Protocol

import yaml

from config.errors import ConfigError
from config.schema import (
    AppConfig,
    DatabaseConfig,
    DeviceControlConfig,
    LoggingConfig,
    MemoryConfig,
    ModelConfig,
    ResourceThresholds,
    SecurityConfig,
    UIConfig,
    VoiceConfig,
    WorkflowConfig,
)

DEFAULT_CONFIG_PATH = Path(__file__).parent / "defaults.yaml"
LOCAL_CONFIG_PATH = Path(__file__).parent / "local.yaml"
ENV_PREFIX = "JARMINEI"
# Single source of truth for every AppConfig section, used by both
# _dict_to_config() and _apply_env_overrides(). Previously these were two
# separately-maintained lists (plus a third, AppConfig's own dataclass
# fields) — Sprint 1.7 added UIConfig to the schema but only updated one
# of the three, so file/env values for it were silently ignored until a
# Sprint 1.8 persistence test caught it. Adding a future section here is
# now the only place needed for both load paths to pick it up.
_SECTION_SCHEMAS: dict[str, type] = {
    "voice": VoiceConfig,
    "resources": ResourceThresholds,
    "database": DatabaseConfig,
    "memory": MemoryConfig,
    "models": ModelConfig,
    "logging": LoggingConfig,
    "ui": UIConfig,
    "device_control": DeviceControlConfig,
    "security": SecurityConfig,
    "workflow": WorkflowConfig,
}


class ConfigSource(Protocol):
    """A source of raw configuration data."""

    def read(self) -> dict:
        ...


class YamlFileConfigSource:
    """Reads a YAML file into a dict. Optional sources tolerate a missing file."""

    def __init__(self, path: Path, required: bool = True) -> None:
        self._path = path
        self._required = required

    def read(self) -> dict:
        if not self._path.exists():
            if self._required:
                raise ConfigError(f"Required config file not found: {self._path}")
            return {}
        try:
            with self._path.open("r", encoding="utf-8") as handle:
                data = yaml.safe_load(handle)
        except yaml.YAMLError as exc:
            raise ConfigError(f"Malformed YAML in {self._path}: {exc}") from exc
        if data is None:
            return {}
        if not isinstance(data, dict):
            # Valid YAML syntax but the wrong shape (e.g. a list or a bare
            # scalar as the whole file) — without this check, the error
            # only surfaces several calls later as a confusing AttributeError
            # or ValueError from _deep_merge()/_dict_to_config(), not here
            # where the actual problem is.
            raise ConfigError(
                f"{self._path} must contain a YAML mapping at the top level, "
                f"got {type(data).__name__}"
            )
        return data


class ConfigLoader:
    """Loads AppConfig from defaults, an optional local overlay, and env overrides."""

    def __init__(
        self,
        defaults_path: Path = DEFAULT_CONFIG_PATH,
        local_path: Path = LOCAL_CONFIG_PATH,
        env: dict[str, str] | None = None,
    ) -> None:
        self._local_path = local_path
        self._defaults_source = YamlFileConfigSource(defaults_path, required=True)
        self._local_source = YamlFileConfigSource(local_path, required=False)
        self._env = env if env is not None else os.environ

    def load(self) -> AppConfig:
        raw = self._defaults_source.read()
        raw = _deep_merge(raw, self._local_source.read())
        raw = self._apply_env_overrides(raw)
        config = _dict_to_config(raw)
        config.validate()
        return config

    def save(self, config: AppConfig, path: Path | None = None) -> None:
        """Persist config to this instance's local overlay (default) or an
        explicit path.

        Uses self._local_path (the local_path this loader was constructed
        with), not the module-level LOCAL_CONFIG_PATH default — otherwise
        a ConfigLoader built with a custom local_path (e.g. in tests, or
        anywhere main.py's default is overridden) would silently save
        somewhere other than where it loads from. Caught in Sprint 1.8,
        the first real caller of save() with path=None.

        Never writes to defaults.yaml — that file is shipped/checked-in;
        edits always go to the gitignored local overlay instead.
        """
        target = path or self._local_path
        with target.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(asdict(config), handle, default_flow_style=False, sort_keys=False)

    def _apply_env_overrides(self, raw: dict) -> dict:
        raw = {key: dict(value) if isinstance(value, dict) else value for key, value in raw.items()}
        for section, schema_cls in _SECTION_SCHEMAS.items():
            prefix = f"{ENV_PREFIX}_{section.upper()}_"
            # Resolved from the schema's own type hints, not from whatever
            # value happens to already be loaded — a field whose section is
            # entirely absent from defaults.yaml/local.yaml still coerces
            # correctly this way (previously fell back to `str`, a bug
            # caught by a Sprint 1.8 test where the ui: section wasn't in
            # the test's minimal defaults fixture).
            field_types = typing.get_type_hints(schema_cls)
            for env_key, env_value in self._env.items():
                if not env_key.startswith(prefix):
                    continue
                field_name = env_key[len(prefix):].lower()
                if field_name not in field_types:
                    continue
                raw.setdefault(section, {})
                raw[section][field_name] = _coerce(env_value, field_types[field_name])
        return raw


def _coerce(value: str, target_type: object):
    """Coerce an env-var string to the schema-declared field type."""
    if target_type is bool:
        return value.lower() in ("1", "true", "yes", "on")
    if target_type is int:
        return int(value)
    if target_type is float:
        return float(value)
    if typing.get_origin(target_type) is list:
        return [item.strip() for item in value.split(",")]
    return value


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _dict_to_config(raw: dict) -> AppConfig:
    try:
        kwargs = {
            section: schema_cls(**raw.get(section, {}))
            for section, schema_cls in _SECTION_SCHEMAS.items()
        }
        return AppConfig(**kwargs)
    except TypeError as exc:
        raise ConfigError(f"Invalid configuration structure: {exc}") from exc


def load_config(path: Path | None = None) -> AppConfig:
    """Convenience wrapper: load the application configuration."""
    if path is not None:
        return ConfigLoader(defaults_path=path).load()
    return ConfigLoader().load()
