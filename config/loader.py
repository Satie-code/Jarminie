"""Load, validate, and persist JARMINEI's configuration.

Precedence (lowest to highest): defaults.yaml -> local.yaml (optional,
gitignored, machine-specific) -> JARMINEI_<SECTION>_<FIELD> environment
variables. See docs/sprint_book/sprint_1_2.md for the design rationale.
"""

from __future__ import annotations

import os
import typing
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import yaml

from config.errors import ConfigError
from config.schema import (
    AnalyticsConfig,
    AppConfig,
    ContextEngineConfig,
    DatabaseConfig,
    DecisionEngineConfig,
    DeviceControlConfig,
    EmotionConfig,
    InternetConfig,
    KnowledgeGraphConfig,
    LearningConfig,
    LoggingConfig,
    MemoryConfig,
    ModelConfig,
    PlanningConfig,
    PresentationConfig,
    ProactiveConfig,
    ReasoningConfig,
    ResourceThresholds,
    RuntimeConfig,
    SchedulerConfig,
    SecurityConfig,
    UIConfig,
    VoiceConfig,
    WellnessConfig,
    WorkflowConfig,
)

if TYPE_CHECKING:
    # security.secret_store is imported lazily inside ConfigLoader.__init__
    # instead, never at this module's own top level: config/__init__.py
    # eagerly imports config.loader, and security.secret_store itself
    # imports core.logging_setup, which imports config.schema — which,
    # the first time anything touches the config package, re-enters
    # config/__init__.py's own still-running import of config.loader
    # before SecretStore's class body has finished executing. A
    # module-level `from security.secret_store import SecretStore` here
    # hits that cycle head-on whenever security.secret_store (or a module
    # that imports it, e.g. presentation/vtube_studio_renderer.py) is
    # the first thing a process imports. Same function-local-import idiom
    # security/policy_engine.py's own docstring already documents for
    # this exact class of problem.
    from security.secret_store import SecretStore

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
    "scheduler": SchedulerConfig,
    "internet": InternetConfig,
    "emotion": EmotionConfig,
    "presentation": PresentationConfig,
    "analytics": AnalyticsConfig,
    "wellness": WellnessConfig,
    "learning": LearningConfig,
    "planning": PlanningConfig,
    "context_engine": ContextEngineConfig,
    "reasoning": ReasoningConfig,
    "decision_engine_v2": DecisionEngineConfig,
    "knowledge_graph": KnowledgeGraphConfig,
    "proactive": ProactiveConfig,
    "runtime": RuntimeConfig,
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
        secret_store: SecretStore | None = None,
    ) -> None:
        self._local_path = local_path
        self._defaults_source = YamlFileConfigSource(defaults_path, required=True)
        self._local_source = YamlFileConfigSource(local_path, required=False)
        self._env = env if env is not None else os.environ
        if secret_store is not None:
            self._secret_store = secret_store
        else:
            from security.secret_store import SecretStore as _SecretStore

            self._secret_store = _SecretStore()

    def load(self) -> AppConfig:
        raw = self._defaults_source.read()
        raw = _deep_merge(raw, self._local_source.read())
        raw = self._apply_env_overrides(raw)
        config = _dict_to_config(raw)
        self._resolve_secrets(config)
        config.validate()
        return config

    def _resolve_secrets(self, config: AppConfig) -> None:
        """Sprint 6.20 — Permission & Encryption Audit. A keyring-stored
        value (via self._secret_store) takes priority over whatever
        _apply_env_overrides() already resolved above. The environment
        fallback here reads self._env — this loader's own injected env
        source — rather than SecretStore's own env_fallback (which reads
        the real process environment directly), so that
        ConfigLoader(env=...) keeps fully isolating tests from the real
        machine's environment, exactly as it already does for every
        other field.
        """
        config.internet.search_api_key = (
            self._secret_store.get_secret("search_api_key")
            or self._env.get("JARMINEI_INTERNET_SEARCH_API_KEY")
            or config.internet.search_api_key
        )
        config.internet.tavily_api_key = (
            self._secret_store.get_secret("tavily_api_key")
            or self._env.get("JARMINEI_INTERNET_TAVILY_API_KEY")
            or config.internet.tavily_api_key
        )

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

        Sprint 6.20 — Permission & Encryption Audit: internet.search_api_key/
        tavily_api_key are real secrets resolved via SecretStore
        (keyring-first) and must never round-trip to this plaintext file —
        forced to null here regardless of what the in-memory AppConfig
        object holds, closing the "env-only discipline is convention, not
        enforced by code" gap.
        """
        target = path or self._local_path
        data = asdict(config)
        data["internet"]["search_api_key"] = None
        data["internet"]["tavily_api_key"] = None
        with target.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(data, handle, default_flow_style=False, sort_keys=False)

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
