# JARMINEI

A personal AI Operating System — not a chatbot. One intelligence, expressed through two personas:

- **Jarvis** — professional, analytical, productivity-focused. Coding, research, scheduling, automation, device control, emergency handling.
- **Minie** — calm, caring, conversational. Casual conversation, wellness, hydration/break reminders, emotional support.

Only one persona is active at a time. Local-first, single-user, Windows laptop for v1. See [docs/](docs/) (starting with [01_Project_Vision.md](docs/01_Project_Vision.md)) for the full engineering specification — that is the project's source of truth. Development follows the sprint-driven workflow in [docs/05_Claude_Development_Guide.md](docs/05_Claude_Development_Guide.md).

## Status

**v0.1.0 released** — Level 1 (Foundation) complete: `main.py` is a real, working PySide6 desktop app with configuration, structured logging, resource monitoring, orchestration, live status, persistent settings, and a live debug console. See [docs/changelog/0.1.0.md](docs/changelog/0.1.0.md) for what shipped, [docs/STATUS.md](docs/STATUS.md) for the full roadmap, and [docs/sprint_book/](docs/sprint_book/) for per-sprint detail. Level 2 (Communication / voice pipeline) is next.

## Tech Stack

Python 3.12+, PySide6, Ollama (Gemma 3 / Phi-4 Mini), Whisper, openWakeWord, Coqui TTS, SQLite, ChromaDB, APScheduler, PyAutoGUI, psutil, pywin32. Full rationale in [docs/03_Engineering_Standards.md](docs/03_Engineering_Standards.md).

## Repository Layout

Each top-level directory owns exactly one subsystem (see [docs/03_Engineering_Standards.md](docs/03_Engineering_Standards.md) and [docs/02_System_Architecture.md](docs/02_System_Architecture.md)):

```
core/            Core Manager — orchestration, startup/shutdown, health monitoring
personas/        Jarvis / Minie persona system and switching rules
voice/           Wake word, STT/TTS, session lifecycle, Quiet Mode
memory/          Shared / persona / event / short-term memory, dynamic confidence scoring
decision/        Intent detection, context analysis, engine selection
authority/       Permission levels (Inform / Recommend / Emergency Assist), priority queue
scheduler/       Calendar, deadlines, events, reminders
workflow/        Automated multi-step action sequences
wellness/        Minie-owned wellness reminders and escalation
emotion/         Stress / fatigue / frustration detection (behavioral, not medical)
analytics/       Productivity, habit, and usage tracking
learning/        Continuous personalization
internet/        Research, search, summarization, source validation
device_control/  Application, file, window, and system control
security/        Permission verification, authentication, encryption, privacy
database/        SQLite-backed structured persistence
ui/              PySide6 desktop interface
config/          Runtime configuration (no secrets or logic)
logs/            Structured runtime logs (gitignored)
tests/           unit/ · integration/ · system/
docs/            Engineering specification, sprint book, changelog, TDs, backlog
assets/          Static assets (icons, voice models, etc.)
scripts/         One-off utility scripts
```

## Development Setup

Requires Python 3.12+.

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt   # dev tooling (pytest, ruff)
pip install -r requirements.txt       # full runtime stack (large; install per-phase as needed, see docs/STATUS.md)
```

See [docs/CODING_STANDARDS.md](docs/CODING_STANDARDS.md) for naming, style, testing, and git conventions before contributing code.
