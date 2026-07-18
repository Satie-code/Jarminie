# Sprint 2.11 — Persona Switching & Explicit Selection

## Sprint ID

2.11

## Sprint Name

Persona Switching & Explicit Selection

## Purpose

Complete Phase 2.3 (Persona Engine) with the switching mechanism itself, per [02_System_Architecture.md](../02_System_Architecture.md)'s Persona Switching Rules: *"Only one persona may be active. Priority: 1. Critical emergency 2. Explicit user selection 3. Context detection 4. Daily routine. Emergency handling temporarily suspends the active persona. After emergency completion: Resume previous session automatically."* This sprint closes Phase 2.3's acceptance criteria: *"Correct persona selected. Correct voice selected. No simultaneous personas."*

## Engineering Rationale

Part 2's four-level priority list is a genuine architectural requirement, but only two of its four inputs have a real source anywhere in Level 1 or Level 2:

- **Critical emergency** — requires the Authority System (Level 3, Sprint 3.11 Authority Evaluation & Engine Selection — renumbered from the original 3.10 placeholder when Level 3 was expanded to full detail on 2026-07-18; see `sprint_book/INDEX.md`'s Level 3 breakdown note). Not built yet.
- **Explicit user selection** — the user says something like "talk to Minie" — detectable now with simple configured trigger phrases, no NLU required.
- **Context detection** — Part 2 implies inferring the appropriate persona from conversation content. Real Context Analysis is Level 3 (Sprint 3.8), built on Intent Detection (Sprint 3.7) and Ollama. A crude keyword-list heuristic is achievable now without pulling in a Decision Engine, and is explicitly labeled as a placeholder for Sprint 3.8 to replace, exactly like Sprint 2.9/2.10's `compose_reply()` placeholders.
- **Daily routine** — requires the Scheduler (Level 4, Sprint 4.8+). Not built yet.

This sprint therefore builds the full priority-ordered switching *mechanism* (so it never needs reshaping later) but wires only Explicit Selection and the heuristic Context Detection to real triggers, leaving the other two reserved and clearly documented — the same pattern already established for `ActivationReason` in Quiet Mode Controller (2.6). This keeps the mechanism spec-complete without pulling emergency/scheduling functionality into Level 2, which this task explicitly excludes.

## Objectives

- A `PersonaManager` holding the single active `Persona` reference, enforcing "no simultaneous personas."
- `select(persona_name, reason)` that only allows a switch when the incoming `reason`'s priority is at or above whatever caused the current active persona (an `EXPLICIT_SELECTION` mid-session should not be silently overridden by a lower-priority heuristic).
- `resume_previous()` per Part 2's "after an interruption, the previous session resumes" — implemented as a mechanism now, even though nothing in Level 2 yet triggers a true interruption (that arrives with Sprint 3.11's emergency wiring).

## Dependencies

2.9 (Persona Base & Jarvis Persona), 2.10 (Minie Persona)

## Files to Create

- `personas/persona_manager.py` — `SwitchReason` (Enum), `PersonaManager`.
- `tests/unit/personas/test_persona_manager.py`

## Files to Modify

- `config/schema.py` — add to `VoiceConfig`: `jarvis_trigger_phrases: list[str] = ["talk to jarvis", "switch to jarvis"]`, `minie_trigger_phrases: list[str] = ["talk to minie", "switch to minie"]` (Explicit Selection input); no changes needed for Context Detection's keyword heuristic, which lives entirely inside `PersonaManager` as a small internal constant, not user-configurable (it is a placeholder, not a tunable feature — promoting it to config would overstate its permanence).

## Expected Classes

- `SwitchReason` (Enum) — `CRITICAL_EMERGENCY` (reserved, priority 1), `EXPLICIT_SELECTION` (priority 2, wired), `CONTEXT_DETECTION` (priority 3, wired as a heuristic placeholder), `DAILY_ROUTINE` (reserved, priority 4). Enum order encodes priority directly, matching Part 2's numbered list.
- `PersonaManager(ManagedModule)` — constructor DI: `(jarvis: Persona, minie: Persona, voice_config: VoiceConfig)`.

## Expected Interfaces

- `ManagedModule` (reused) — `start()` sets the default active persona (Jarvis, per Part 2 characterizing Jarvis as the default "system brain" for general interaction, Minie activating contextually); `stop()` is a no-op beyond logging (no external resource owned); `health_check()` confirms exactly one persona is active.

## Expected Functions

- `PersonaManager.select(persona_name: str, reason: SwitchReason) -> bool` — returns whether the switch was applied; refuses (logged, not raised) a lower-priority `reason` from displacing a currently-active higher-priority selection. Records the displaced persona + reason so `resume_previous()` can restore it.
- `PersonaManager.resume_previous() -> None` — restores whatever persona/reason was active before the most recent successful higher-priority switch; a no-op (logged) if nothing is recorded to resume.
- `PersonaManager.active_persona() -> Persona`
- `PersonaManager.detect_explicit_selection(transcript: str) -> str | None` — checks `transcript` against `jarvis_trigger_phrases`/`minie_trigger_phrases`, returns the matched persona name or `None`.
- `PersonaManager.detect_context_heuristic(transcript: str) -> str | None` — small internal keyword-list placeholder (e.g. casual/emotional words → Minie, technical/project words → Jarvis); returns `None` when no heuristic matches, explicitly documented as a Sprint 3.8 replacement candidate.

## Data Flow

```
Transcript (from VoiceSessionManager, 2.5) + ConversationContext (2.8)
      ↓
PersonaManager.detect_explicit_selection(transcript) → persona_name | None
      ↓ (if None)
PersonaManager.detect_context_heuristic(transcript) → persona_name | None
      ↓ (whichever matched, with its SwitchReason)
PersonaManager.select(persona_name, reason)
      ↓ (priority check passes)
active persona updated → Persona.compose_reply() / TextToSpeech voice_id
```

## Acceptance Criteria

- Exactly one persona is active at any time — no code path can leave zero or two active.
- An explicit selection ("talk to Minie") switches the active persona and its voice correctly.
- A `CONTEXT_DETECTION` match cannot override a persona made active via `EXPLICIT_SELECTION` in the same session (priority respected).
- `resume_previous()` restores the prior persona when called (verified with a fake higher-priority interruption in tests, since no real emergency trigger exists yet).
- This sprint's completion satisfies Phase 2.3's full acceptance criteria in combination with 2.9–2.10.

## Testing Checklist

- [ ] Unit: `select()` with equal-or-higher priority than the current reason succeeds; lower priority is refused and logged.
- [ ] Unit: `detect_explicit_selection()` matches configured trigger phrases case-insensitively; returns `None` for unrelated text.
- [ ] Unit: `detect_context_heuristic()` matches its placeholder keyword lists; returns `None` otherwise.
- [ ] Unit: `resume_previous()` restores the correct prior persona after a simulated higher-priority interruption.
- [ ] Unit: `health_check()` fails if internal state ever ends up with zero or more than one "active" flag set (defensive test against a bug class, not an expected real path).

## Documentation Checklist

- [ ] `personas/persona_manager.py` docstring: full priority table with wired/reserved status per reason, cross-referencing Sprint 3.11 (emergency) and Sprint 4.8+ (daily routine/scheduler) as where the reserved reasons get real callers.
- [ ] `docs/STATUS.md` — Phase 2.3 (Persona Engine) marked **Complete**.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md). This sprint also closes Phase 2.3 (Persona Engine) and, in combination with 2.1–2.10, all of Level 2's individual-component sprints.

## Estimated Complexity

Medium-High — the priority-ordered switching/resume logic has more edge cases (simultaneous triggers, resume-of-resume) than its component count suggests.

## Estimated Development Time

1.5–2 days.

## Risks

- **`detect_context_heuristic()`'s keyword lists are a known-crude placeholder** — likely to misclassify in practice; acceptable for Level 2, explicitly scheduled for replacement by Sprint 3.8's real Context Analysis, not a hidden permanent limitation.
- **Resume-of-resume semantics** (an interruption occurring while already resuming from a prior one) are under-specified by Part 2's text and not fully solved here — if Sprint 3.11's real emergency wiring exposes a genuine gap, that is the point to redesign `resume_previous()`'s stack behavior, not a flaw to over-engineer against speculatively now.
- **Emotional/wellness-based persona routing** (Minie's real trigger conditions per Part 1/2) remains entirely unbuilt until Level 5 — the context heuristic here is topic-based only, not emotion-based; do not conflate the two when Level 5 arrives.

## Next Sprint

2.12 — Communication Pipeline Integration.

## Sprint Completion Report (2026-07-17)

Delivered the files this sprint's spec named:

- `personas/persona_manager.py` — `SwitchReason` (Enum, declaration order = priority), `PersonaManager(ManagedModule)`.
- `tests/unit/personas/test_persona_manager.py` — 20 tests.
- `config/schema.py` — `VoiceConfig.jarvis_trigger_phrases`/`minie_trigger_phrases` added, plus validation (non-empty, no blank entries) in `_validate_voice()`, mirroring the existing `wake_phrases` pattern; `config/defaults.yaml` updated to match. 4 new tests added to `tests/unit/config/test_schema.py` for this validation — not explicitly called out in the sprint's own Testing Checklist, but a natural extension of the already-established `wake_phrases` validation convention for a new field of the same shape, not a new feature.

251/251 tests passing project-wide (227 prior + 24 new), `ruff check .` clean.

**All Acceptance Criteria met**: exactly one persona is active at all times, verified both through normal operation sequences (`test_exactly_one_persona_active_across_a_sequence_of_operations`) and defensively — `health_check()` correctly fails when the internal per-persona active-flag dict is deliberately corrupted to zero or two flags set, which is *why* active state is tracked as a flag dict rather than a single reference (a single reference would make "two active" structurally impossible to simulate, defeating the point of this sprint's own defensive Testing Checklist item). An explicit selection ("talk to minie") switches both the active persona and its `voice_id` correctly. `CONTEXT_DETECTION` cannot override a persona active via `EXPLICIT_SELECTION` — confirmed directly. `resume_previous()` restores the correct prior persona after a simulated `CRITICAL_EMERGENCY` interruption (no real emergency trigger exists until Sprint 3.11 [renumbered from 3.10 — see `sprint_book/INDEX.md`'s Level 3 breakdown note], so the sprint's own Acceptance Criteria explicitly call for a fake higher-priority interruption in tests) and is a no-op, logged, when nothing is recorded to resume.

**One design decision made during implementation, not literally specified, recorded here**: active-persona state is a `dict[str, bool]` of per-persona flags (`_active_flags`) plus a `_active_name: str | None` pointer, rather than a single `Persona | None` reference. This is what makes "confirms exactly one persona is active" (Expected Interfaces' `health_check()` description) and the Testing Checklist's explicit "fails if internal state ever ends up with zero or more than one active flag set" item both literally testable — a test can directly corrupt `_active_flags` to simulate the bug class being defended against, which a single-reference design would make structurally impossible to even express.

**Placeholder discipline maintained per this sprint's own Risks**: `detect_context_heuristic()`'s keyword lists (`_MINIE_HEURISTIC_KEYWORDS`/`_JARVIS_HEURISTIC_KEYWORDS`) are a small, non-configurable module-level constant, explicitly documented as a known-crude Sprint 3.8 replacement candidate — not promoted to `VoiceConfig`, per the spec's own instruction that doing so would overstate its permanence. `resume_previous()` tracks exactly one prior (persona, reason) pair, not a stack (`test_resume_previous_only_restores_one_level` confirms a second call after a completed resume is a no-op) — deeper resume-of-resume semantics are deliberately left unsolved, per the spec's explicit caution against over-engineering ahead of Sprint 3.11's real emergency wiring.

This sprint closes Phase 2.3 (Persona Engine) **and, in combination with Sprints 2.1–2.10, all of Level 2's individual-component sprints** — `docs/STATUS.md` updated accordingly. **Sprint 2.12 (Communication Pipeline Integration) is next** — the first sprint that actually wires `main.py`/`CoreManager` to every component built across 2.1–2.11 (every one of those sprints deliberately left `main.py` untouched for exactly this reason).

## Post-Sprint Fix (2026-07-17, post-release real-hardware testing)

Real end-to-end use on the actual target laptop showed Whisper (Sprint 2.3) mishearing "talk to minie" as "talk to my knee" — the exact substring match `detect_explicit_selection()` performs against `VoiceConfig.minie_trigger_phrases` correctly never matched "my knee" against "minie", since it isn't the same text; the bug is upstream in speech recognition, not in this module's own matching logic. See `sprint_2_3.md`'s Post-Sprint Fix for the primary fix (Whisper's `initial_prompt` biasing).

**Fix (the safety-net half)**: `VoiceConfig.minie_trigger_phrases`' default expanded from 2 entries to include "talk to/switch to my knee" and "talk to/switch to minnie" — still exact case-insensitive substring matching, no fuzzy logic or NLU added, consistent with this sprint's own "no NLU required" design. `jarvis_trigger_phrases` unchanged (no mishearing reported for "Jarvis").

**Verification**: 1 new test (`test_detect_explicit_selection_matches_common_minie_mishearings`) confirming both new variants resolve to "minie". Full suite passing, `ruff check .` clean. Tracked as `backlog/technical_debt.md` item 12.
