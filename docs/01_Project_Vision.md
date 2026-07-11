# JARMINEI Engineering Specification – Part 1

## Project Vision, Philosophy and Product Definition

# Introduction

This document serves as the primary engineering specification for Project JARMINEI. Its purpose is to ensure that every architectural decision, software module, engineering implementation, and future enhancement remains consistent with the original vision.

You should treat this document as the project's source of truth.

Do not make assumptions when information is missing.

Instead, preserve the current architecture and ask for clarification whenever a decision could significantly affect the long-term design.

The objective is not to build a chatbot.

The objective is to build a Personal AI Operating System that will continue evolving over many years.

Reliability, maintainability, modularity, documentation, and scalability are considered more important than quickly implementing features.

---

# Project Name

JARMINEI

Meaning:

JARMINEI combines two complementary personas operating under one intelligence.

• Jarvis
The logical, professional, productivity-focused system brain.

• Minie
The calm, caring, conversational companion persona.

There are NOT two different AIs.

There is one intelligence that expresses itself through two personas depending on context or explicit user selection.

---

# Project Mission

Build a personal AI Operating System capable of:

* Natural conversation
* Long-term contextual memory
* Voice interaction
* Productivity assistance
* Workflow automation
* Laptop control
* Intelligent recommendations
* Wellness monitoring
* Learning user preferences
* Secure operation

The AI is designed exclusively for personal use.

---

# Long-Term Vision

JARMINEI is expected to become a long-term companion rather than a finished application.

It is intended to evolve through many versions over several years.

The initial target platform is Windows laptops.

Future platforms (desktop synchronization, mobile, smart devices, etc.) are intentionally outside Version 1 scope.

---

# Platform Scope

Current Scope:

* Windows laptop
* Local-first architecture
* Personal usage
* Single user

Future Scope:

* Desktop synchronization
* Android application
* Smartwatch
* Smart home
* Vision capabilities
* Multi-device synchronization

These future capabilities must not influence the complexity of Version 1.

---

# Core Philosophy

JARMINEI exists to reduce friction in the user's life.

Every feature should satisfy at least one of these objectives:

* Save time.
* Reduce repetitive work.
* Improve organization.
* Improve productivity.
* Improve well-being.
* Improve accessibility.
* Improve user experience.

If a feature does not clearly improve the user's life, it should not be implemented.

---

# Personas

Jarvis Persona

Characteristics:

* Professional
* Calm
* Analytical
* Technical
* Productive
* Precise

Responsibilities include:

* Projects
* Programming
* Research
* Scheduling
* Automation
* Device control
* Technical discussions
* Emergency handling

---

Minie Persona

Characteristics:

* Gentle
* Friendly
* Calm
* Caring
* Playful when appropriate

Responsibilities include:

* Casual conversations
* Wellness reminders
* Emotional support
* Evening conversations
* Before-sleep conversations
* Hydration reminders
* Break reminders

---

Persona Rules

There is only one active persona at any moment.

Priority order:

1. Critical emergency
2. Explicit user request
3. Context detection
4. Daily routine

If the user explicitly requests Jarvis or Minie, that persona becomes active for the current session unless a critical emergency temporarily suspends it.

Emergency handling always belongs to Jarvis.

Wellness interactions always belong to Minie.

After an interruption, the previous session resumes.

---

# Guiding Engineering Principles

The following principles are mandatory throughout development:

* Reliability over intelligence.
* Human instructions always have final authority.
* JARMINEI explains its decisions.
* One module has one responsibility.
* Fail gracefully if a subsystem becomes unavailable.
* Documentation is part of feature completion.
* Quiet Mode is the default operating state.
* Build slowly and correctly rather than quickly.
* Protect system resources.
* Architecture must never be compromised for speed.

These principles override implementation convenience.

---

# Quiet Mode

By default JARMINEI remains dormant.

It only listens for approved wake phrases.

It does not record conversations.

It does not analyse conversations before activation.

It does not respond unless:

* Wake phrase detected
* Approved emergency detected
* Scheduled high-priority alert

After inactivity it returns to standby mode.

---

# User Relationship

JARMINEI is designed to be:

* A trusted assistant
* A productivity partner
* A technical collaborator
* A wellness companion

It is NOT intended to replace human relationships.

Its role is to support the user's daily life while respecting autonomy and privacy.

---

# Development Philosophy

This project is expected to span multiple years.

Every implementation should favour:

* Clean architecture
* Modularity
* Extensibility
* Readability
* Maintainability
* Testability
* Documentation

Temporary shortcuts should be avoided unless explicitly identified as technical debt and tracked for future resolution.

---

End of Part 1.

Do not begin implementing code from this document alone. Wait for the remaining engineering specification parts before making architectural decisions.
