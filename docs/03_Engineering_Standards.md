# JARMINEI Engineering Specification – Part 3

## Engineering Standards, Technology Stack & Development Guidelines

# Introduction

This document defines the engineering standards for Project JARMINEI.

Unlike the previous documents, this specification focuses on software engineering practices rather than product functionality.

Its purpose is to ensure that the codebase remains maintainable, scalable, understandable, and production-ready throughout the lifetime of the project.

Every implementation should follow this document unless an explicit architectural decision supersedes it.

---

# Development Philosophy

JARMINEI is a long-term engineering project.

The objective is not rapid feature delivery.

The objective is sustainable software engineering.

Every implementation should prioritize:

* Reliability
* Readability
* Maintainability
* Modularity
* Testability
* Documentation
* Scalability

Performance optimizations should never reduce code quality unless absolutely necessary.

---

# Technology Stack

## Programming Language

Primary Language:

Python 3.12+

Python will be used for all application logic.

---

## Desktop Framework

PySide6

Purpose:

* Native desktop interface
* Settings
* Dashboard
* Future visual tools

---

## AI Runtime

Ollama

Purpose:

Run local language models.

Initial supported models:

* Gemma 3
* Phi-4 Mini

The architecture must remain model-independent so that additional models can be integrated later without significant refactoring.

---

## Speech Recognition

Whisper

Purpose:

Speech-to-text.

The Speech-to-Text interface should remain abstract enough to support future engines.

---

## Wake Word

openWakeWord

Purpose:

Always-on wake phrase detection.

No other speech should be processed before successful wake word activation.

---

## Text-to-Speech

Coqui TTS

Supports:

Jarvis Voice

Minie Voice

Voice selection should be handled through the Persona System rather than hardcoded.

---

## Database Layer

SQLite

Purpose:

Structured persistent data.

Examples:

Configuration

Goals

Projects

Schedules

Settings

---

## Semantic Memory

ChromaDB

Purpose:

Semantic retrieval.

Conversation memory.

Context search.

Long-term knowledge.

---

## Cache Layer

Not JSON-file-based caching, as originally planned here — evaluated and deliberately not built this way (Sprint 6.16's own dedicated investigation found no genuine duplicate-recompute pattern anywhere in the real call paths; see `backlog/technical_debt.md` item 61).

What actually serves this purpose:

`core/runtime_manager.py`'s `RuntimeManager` — lazy-loaded, tiered service construction and eviction, not a persistence-based cache.

A deliberate "recompute fresh, never cache" discipline for working-context data instead (`context/context_model.py`, `voice/context_manager.py`, each module's own docstring).

`config/` (Sprint 1.2) already covers configuration persistence; no separate JSON cache file was ever needed for it.

---

## Scheduling

APScheduler

Responsibilities:

Delayed reminders.

Scheduled jobs.

Periodic maintenance.

---

## Automation

`pywin32`, not PyAutoGUI — corrected per Level 4's own real implementation (`device_control/application_manager.py`, `device_control/window_manager.py`). `pyautogui` remains declared in `requirements.txt` but was never installed and has zero imports anywhere in the codebase; see `backlog/technical_debt.md` item 61.

Purpose:

Desktop automation.

Keyboard.

Mouse.

Application control.

---

## System Monitoring

psutil

Responsibilities:

CPU

RAM

Battery

Disk

Resource monitoring.

---

## Windows Integration

pywin32

Purpose:

Native Windows functionality.

System-level operations.

---

# Repository Structure

The repository should remain modular.

Top-level directories:

core/

personas/

voice/

memory/

decision/

scheduler/

workflow/

wellness/

analytics/

learning/

internet/

device_control/

security/

database/

ui/

config/

logs/

tests/

docs/

assets/

scripts/

context/

emotion/

knowledge/

planning/

presentation/

proactive/

reasoning/

Each directory should own one subsystem.

Cross-module dependencies should remain minimal.

---

# Project Organization Rules

Every directory should satisfy:

High cohesion.

Low coupling.

Single responsibility.

Reusable interfaces.

Subsystems communicate through well-defined interfaces rather than direct implementation knowledge.

---

# Naming Conventions

Folders

snake_case

Python Files

snake_case

Classes

PascalCase

Functions

snake_case

Variables

snake_case

Constants

UPPER_CASE

Private members

Prefix with underscore.

---

# Code Style

Follow:

PEP 8

Use:

Type hints

Docstrings

Meaningful variable names

Avoid:

Magic numbers

Large functions

Nested conditionals

Duplicated logic

Functions should generally perform one task.

---

# Logging Strategy

Every subsystem should maintain structured logs.

Log Levels:

DEBUG

INFO

WARNING

ERROR

CRITICAL

Logs should include:

Timestamp

Subsystem

Severity

Message

Sensitive personal information should never be logged.

---

# Configuration Management

All configurable values should remain outside the source code.

Examples:

Wake phrases

Reminder intervals

Voice selection

Resource thresholds

Database paths

Model selection

Configurations should be loaded during startup.

---

# Dependency Injection

Subsystems should receive dependencies rather than creating them internally.

Example:

Avoid:

Creating MemoryEngine inside WorkflowEngine.

Instead:

WorkflowEngine receives a MemoryEngine instance.

This improves testing and modularity.

---

# Interface First Design

Subsystems should depend on interfaces whenever possible.

Implementation should remain replaceable.

Example:

SpeechToText Interface

↓

Whisper Implementation

↓

Future implementation

without changing higher-level modules.

---

# Error Handling

Every recoverable error should:

Be logged.

Be reported appropriately.

Avoid crashing unrelated systems.

Never silently ignore exceptions.

---

# Testing Strategy

Three testing levels:

Unit Testing

Individual module validation.

Integration Testing

Communication between modules.

System Testing

Entire application validation.

No major feature is complete without passing all required tests.

---

# Definition of Done

A module is complete only if:

Implementation complete.

Unit tests pass.

Integration tests pass.

Documentation updated.

Logs verified.

No critical issues remain.

Architecture respected.

Only then can it be marked Complete.

---

# Documentation Standards

Every subsystem should include:

Purpose

Responsibilities

Dependencies

Public API

Known limitations

Future improvements

Documentation should evolve alongside implementation.

---

# Git Workflow

**Real practice diverges from this section's original plan — corrected here, not merely flagged, per Sprint 6.22's own "Update" instruction; see `backlog/technical_debt.md` item 62.** All ~130 sprints across Levels 1–6 Part A have been committed directly to `main`; no feature branches have ever existed in this repository. `05_Claude_Development_Guide.md`'s own Step 9 (self-review before a sprint is considered done) substitutes for a branch-based code-review step. Testing and Documentation remain required before a sprint is considered done regardless (see Definition of Done, above).

Suggested Commit Style:

feat:

fix:

refactor:

docs:

test:

chore:

Applied inconsistently in practice — many real commits use a plain, descriptive message instead (e.g. "Add unit tests for X," "Implement Y"); both forms genuinely coexist in this repository's own history, confirmed via `git log`.

Example:

feat(memory): implement dynamic confidence scoring

---

# Versioning Strategy

Follow Semantic Versioning.

Major

Architecture-changing releases.

Minor

New features.

Patch

Bug fixes.

Examples:

0.1.0

0.2.0

0.3.0

1.0.0

---

# Performance Guidelines

Startup should remain lightweight.

Background tasks should be asynchronous whenever possible.

Avoid unnecessary polling.

Cache expensive operations.

Monitor resource usage continuously.

Never sacrifice responsiveness for unnecessary intelligence.

---

# Security Guidelines

Default:

Local-first.

Encrypt sensitive data.

Never expose private information without explicit approval.

Permission-sensitive actions must require confirmation.

Security should be integrated throughout development rather than added afterwards.

---

# Documentation First Rule

No feature is complete until:

Documentation

Tests

Logs

Implementation

are all complete.

---

# Build Philosophy

Every commit should leave JARMINEI in a healthier state than before.

The project should compile, launch, and remain stable after every completed task.

The main branch should always represent a working system.

---

# Engineering Goal

The ultimate objective is not simply to build an AI assistant.

The objective is to engineer a reliable, maintainable Personal AI Operating System capable of evolving for many years without requiring architectural redesign.

End of Part 3.

Do not begin implementation until all Engineering Specification documents have been reviewed.
