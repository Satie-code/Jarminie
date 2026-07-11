# Coding Standards

Reference implementation of the rules defined in [03_Engineering_Standards.md](03_Engineering_Standards.md). This file is the quick-lookup version; the spec document is authoritative if they ever disagree.

## Naming

| Element | Convention |
|---|---|
| Folders | `snake_case` |
| Python files | `snake_case` |
| Classes | `PascalCase` |
| Functions | `snake_case` |
| Variables | `snake_case` |
| Constants | `UPPER_CASE` |
| Private members | leading `_underscore` |

## Style

- Follow PEP 8 (enforced via `ruff` — see `pyproject.toml`).
- Type hints on all public function signatures.
- Docstrings on all public modules, classes, and functions.
- Avoid magic numbers, large functions, nested conditionals, duplicated logic.
- One task per function.

## Architecture rules that affect how code is written

- **Dependency injection**: a subsystem receives its dependencies through its constructor; it never instantiates another subsystem internally (e.g. `WorkflowEngine.__init__(self, memory: MemoryEngine, ...)`, never `self.memory = MemoryEngine()` inside `WorkflowEngine`).
- **Interface-first design**: cross-subsystem contracts are defined as abstract base classes / protocols (e.g. `SpeechToText`) with concrete implementations (`WhisperSpeechToText`) injected in — callers depend on the interface, not the implementation.
- **Single responsibility**: one module, one job. If a file starts doing two unrelated things, split it.
- **Error handling**: catch only what you can meaningfully handle; log every recoverable error with subsystem + severity + message; never use a bare `except: pass`; a failure in one subsystem must not take down the Core or unrelated subsystems (see Fail Gracefully in Part 2).
- **Logging**: use the shared logger per subsystem, levels `DEBUG/INFO/WARNING/ERROR/CRITICAL`; never log conversation content, credentials, or other personal data.
- **Configuration**: no hardcoded wake phrases, intervals, thresholds, paths, or model names — these load from `config/` at startup.

## Definition of Done (per module)

A module is only "Complete" when all of the following hold:

1. Implementation complete.
2. Unit tests pass.
3. Integration tests pass.
4. Documentation updated (purpose, responsibilities, dependencies, public API, known limitations, future improvements).
5. Logs verified.
6. No critical issues remain.
7. Architecture respected.

## Git workflow

- One branch per feature.
- Merge only after review + tests + docs.
- Commit prefixes: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:` — e.g. `feat(memory): implement dynamic confidence scoring`.

## Versioning

Semantic Versioning: `MAJOR.MINOR.PATCH` — major = architecture-changing, minor = new feature, patch = bug fix.
