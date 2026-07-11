# JARMINEI Engineering Specification – Part 2

## Complete Software Architecture

# Introduction

This document defines the complete software architecture of Project JARMINEI.

The purpose of this document is to explain every subsystem, its responsibilities, relationships with other modules, and the governing rules that control their interactions.

This document defines architecture only.

It does NOT define implementation details or code.

The architecture described here should remain stable throughout the project lifecycle.

Implementation may evolve.

Architecture should not.

---

# High-Level Architecture

JARMINEI is designed as a modular AI Operating System.

It is NOT one monolithic application.

Instead, it consists of independent subsystems coordinated by a central Core Manager.

Every subsystem has one responsibility.

Every subsystem must be replaceable without affecting the rest of the system.

The overall hierarchy is:

User
↓
Wake Word Engine
↓
Quiet Mode
↓
JARMINEI Core
↓
Decision Engine
↓
Specialized Engines
↓
Operating System

---

# JARMINEI Core

The Core is the orchestrator.

Responsibilities:

* Initialize all modules.
* Maintain system state.
* Coordinate communication between engines.
* Manage startup and shutdown.
* Monitor module health.
* Handle module registration.
* Restart recoverable modules if necessary.

The Core should contain minimal business logic.

Its primary purpose is orchestration.

---

# Decision Engine

The Decision Engine is responsible for reasoning about requests.

Pipeline:

Input
↓
Intent Detection
↓
Context Analysis
↓
Memory Retrieval
↓
Priority Evaluation
↓
Authority Evaluation
↓
Engine Selection
↓
Execution
↓
Response Generation

Responsibilities:

* Understand user intent.
* Select the correct subsystem.
* Determine response priority.
* Resolve conflicts.
* Maintain explainability.

---

# Persona System

JARMINEI contains one intelligence with two behavioral personas.

## Jarvis

Purpose:

Professional execution.

Responsibilities:

* Coding
* Technical discussions
* Project management
* Research
* Device control
* Scheduling
* Emergency handling
* Productivity

Voice:

Professional male voice.

---

## Minie

Purpose:

Companion behavior.

Responsibilities:

* Casual conversations.
* Wellness.
* Hydration reminders.
* Break reminders.
* Emotional awareness.
* Evening conversations.
* Before-sleep conversations.

Voice:

Soft female voice.

---

# Persona Switching Rules

Only one persona may be active.

Priority:

1. Critical emergency
2. Explicit user selection
3. Context detection
4. Daily routine

Emergency handling temporarily suspends the active persona.

After emergency completion:

Resume previous session automatically.

---

# Voice Engine

Components:

Wake Word Detector

Microphone Manager

Speech-to-Text

Text-to-Speech

Session Manager

Session Timeout

Responsibilities:

Detect wake phrase.

Remain dormant before activation.

Convert speech into text.

Generate spoken responses.

Return to standby after inactivity.

Microphone Rule:

Before wake word:

Only detect wake phrase.

No conversation recording.

No memory creation.

No analysis.

---

# Quiet Mode

Quiet Mode is the default operating state.

JARMINEI remains dormant until:

* Wake phrase.
* Approved emergency.
* High-priority scheduled alert.

This prevents unwanted interaction and unnecessary resource usage.

---

# Memory Architecture

Memory is divided into multiple layers.

## Shared Memory

Accessible by both personas.

Stores:

Projects

Goals

Skills

Important routines

Important life events

Long-term preferences

---

## Jarvis Memory

Stores:

Technical discussions

Project workflows

Programming context

Research

Automation history

---

## Minie Memory

Stores:

Casual conversations

Comfort topics

Humor preferences

Wellness history

Emotional context

---

## Event Memory

Stores permanent milestones.

Examples:

Major projects

Career milestones

Important achievements

Never automatically deleted.

---

## Short-Term Memory

Stores temporary context.

Examples:

Current conversation.

Recent searches.

Temporary tasks.

Automatically expires according to the Dynamic Memory Formula.

---

# Dynamic Memory Formula

Every memory receives a confidence score.

Factors:

Frequency

Recency

Importance

Category

Emotional significance

Score ranges:

0–29

Temporary

30–49

Short-term

50–69

Monthly review

70–89

Long-term

90–100

Permanent

---

# User Override Rule

When the user explicitly states:

Remember this.

Never forget this.

This is important.

The memory immediately receives maximum confidence.

Automatic deletion is disabled.

---

# Authority System

Authority Levels:

Level 1

Inform

No actions.

Only information.

---

Level 2

Recommend

Suggest actions.

User retains control.

---

Level 3

Emergency Assist

Execute previously approved emergency procedures.

Examples:

Battery protection

System overheating

Critical resource management

Emergency actions never include:

Deleting files

Sending messages

Purchasing

Installing software

Sharing information

Those always require approval.

---

# Priority Queue System

Priority determines execution order.

Priority 1

Critical emergency

Immediate interruption.

Priority 2

Important alerts

Wait for natural pause.

Priority 3

Scheduled reminders

Queued.

Priority 4

Wellness

Context-aware reminders.

Priority 5

General suggestions.

Lowest priority.

---

# Workflow Engine

Purpose:

Automate repetitive actions.

Example:

Continue Project JARMINEI.

↓

Open IDE

↓

Open project folder

↓

Restore workspace

↓

Display pending tasks

Large workflow rule:

If many actions are about to execute,

request confirmation before proceeding.

---

# Scheduler Engine

Responsibilities:

Calendar

Deadlines

Events

Reminders

Delayed reminders

Reminder rescheduling

Wellness postponement

---

# Wellness Engine

Owned exclusively by Minie.

Responsibilities:

Screen time

Hydration

Eye protection

Break reminders

Late-night reminders

Overwork awareness

Adaptive wellness

Soft Wellness Rule:

Recommend.

Never force.

Adaptive Wellness Rule:

Learn work patterns.

Adjust reminders accordingly.

Wellness Escalation:

Reminder 1

Gentle.

Reminder 2

Slightly stronger.

Reminder 3

Strong recommendation.

Hard Limit Rule:

Stop repeated reminders after three postponements.

Resume after:

New session.

Actual break.

Significant inactivity.

---

# Emotion Engine

Purpose:

Behavioral awareness.

Detect:

Stress

Fatigue

Frustration

Detection sources:

Voice characteristics.

Speech pace.

Interaction patterns.

Repeated failures.

The Emotion Engine never diagnoses medical conditions.

Its purpose is contextual adaptation.

---

# Learning Engine

Purpose:

Continuous personalization.

Learn:

Preferred study times.

Frequently used applications.

Common workflows.

Work habits.

Preferred conversation style.

The Learning Engine may recommend improvements.

It never makes major autonomous decisions.

---

# Analytics Engine

Tracks:

Productivity

Habit consistency

Project progress

Focus sessions

Screen time

Application usage

Statistics are used only for improving user experience.

---

# Internet Agent

Responsibilities:

Research.

Search.

Summarization.

Source comparison.

Source validation.

The Internet Agent should prioritize trustworthy sources.

It should clearly distinguish between verified facts and uncertain information.

---

# Device Control Engine

Controls:

Applications

Windows

Files

Folders

System settings

Automation

System monitoring

Permission-sensitive operations always require user approval.

---

# Security Layer

Acts as a gatekeeper.

Every high-impact operation passes through Security.

Responsibilities:

Permission verification

Authentication

Encryption

Privacy protection

Safe execution

---

# Resource Protection

JARMINEI continuously monitors:

CPU

GPU

RAM

Storage

Battery

If thresholds are exceeded,

background work is reduced before the system becomes unresponsive.

The user should never experience degraded usability because of JARMINEI.

---

# Explainability Rule

Every recommendation, reminder and action should have an explainable reason.

The user may ask:

Why?

JARMINEI should always provide the reasoning behind its behavior.

---

# Fail Gracefully Rule

Failure of one subsystem must never terminate the entire application.

Unavailable modules should report their status while allowing the remaining modules to continue functioning.

---

# Human First Rule

The user's decision always overrides recommendations.

JARMINEI advises.

The user decides.

---

# Single Responsibility Rule

Every subsystem and every major module should have one clearly defined responsibility.

This principle applies throughout the entire codebase.

---

# Architecture Goal

The architecture prioritizes:

Reliability

Maintainability

Scalability

Modularity

Security

Privacy

Explainability

Extensibility

These principles should guide every future engineering decision.

End of Part 2.

Do not begin implementation based only on Parts 1 and 2. Wait for the complete Engineering Specification before generating production code.
