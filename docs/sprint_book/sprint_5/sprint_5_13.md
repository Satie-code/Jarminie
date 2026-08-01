# Sprint 5.13 — Companion Experience

## Sprint ID

5.13

## Sprint Name

Companion Experience

## Purpose

Assemble greetings, idle behavior, celebrations, context awareness, and relationship continuity — the brief's own named companion-experience list — from capability every prior Part A sprint already built. This sprint is deliberately almost entirely **composition**, not new mechanism: it is where JARMINEI's presentation layer stops being a set of independently correct parts and starts feeling, per the brief's own mission statement, "alive."

## Engineering Rationale

**New sprint**, and the last component sprint before Part A's own integration/hardening/freeze trio (5.14–5.16). Explicitly composes, never duplicates:

- **Greetings**: keyed off real idle duration since the last session (`ConversationSessionStore`, Sprint 2.7 — already real, already persisted; this sprint reads it, adds nothing to it).
- **Idle behaviors**: delegates entirely to `GestureEngine.maybe_roll_ambient_gesture()`/`GestureTrigger.AMBIENT_IDLE` (Sprint 5.9) — this sprint does not build a second idle-gesture mechanism (explicitly named as a risk to avoid in Sprint 5.9's own Integration Considerations).
- **Celebrations**: triggered by `EmotionalMemory.recall_recent_moments()` (Sprint 5.3) surfacing a high-significance record, or by `EventMemory`'s own existing permanent milestones (Sprint 3.3) — both already real.
- **Relationship continuity**: a natural greeting referencing a past `EmotionalMemory` record ("last time we talked you mentioned X") — the brief's own explicit example.
- **Wellness reminders**: explicitly **named, not built** — Part B's own Wellness Engine (sprints 5.17–5.19, roadmap granularity only per `docs/sprint_book/INDEX.md`) owns that capability entirely; this sprint leaves one clearly-marked extension point (see Integration Considerations) and builds nothing wellness-shaped itself, the same discipline every prior sprint in this Level applied to out-of-scope Part B territory.

**Deliberately Minie-flavored by default, persona-agnostic in the engine itself** — mirrors `GestureEngine`'s own established when/how split: `CompanionExperienceEngine` decides *that* a greeting/celebration/continuity-callback is warranted and *what content* it should reference (a `CompanionMoment` dataclass), never *how* it's phrased or rendered — phrasing goes through the already-adapted `Persona.compose_reply()`/`VoicePersonalityModulator` path (Sprint 5.4/5.11), rendering through whichever `Renderer` is mounted (Sprint 5.6). This sprint adds no new phrasing-generation or rendering code of its own.

## Objectives

- `presentation/companion_experience.py`: `CompanionMoment` dataclass, `CompanionMomentType` enum (`GREETING`, `CELEBRATION`, `CONTINUITY_CALLBACK`), `CompanionExperienceEngine`.
- `check_for_greeting()`, `check_for_celebration()`, `check_for_continuity_callback()` — each independently callable, each returning `CompanionMoment | None`.

## Dependencies

5.3 (Emotional Memory), 5.9 (Gesture Engine), 3.1–3.4 (Memory Engine).

## Files to Create

- `presentation/companion_experience.py`
- `tests/unit/presentation/test_companion_experience.py`

## Files to Modify

- `config/schema.py` — `PresentationConfig` gains `greeting_idle_threshold_seconds: float = 3600.0` (one hour — below this, no special greeting; above it, a "welcome back" style moment is warranted), `celebration_significance_threshold: float = 0.75` (a higher bar than `MemoryConfig.emotional_moment_recall_threshold`'s own general-recall threshold — a celebration should be reserved for genuinely standout moments, not merely "significant enough to recall").

## Expected Classes

- **`CompanionMomentType`** (`Enum`): `GREETING`, `CELEBRATION`, `CONTINUITY_CALLBACK`.
- **`CompanionMoment`** (dataclass): `moment_type: CompanionMomentType`, `referenced_content: str | None` (the memory content being referenced, if any — `None` for a plain greeting with nothing specific to reference), `referenced_at: datetime | None` (when the referenced memory/event originally happened, for a natural "last time..." framing), `detected_at: datetime`.
- **`CompanionExperienceEngine`**: constructor DI receives `EmotionalMemory` (5.3), `EventMemory` (existing, Sprint 3.3), and `PresentationConfig`.

## Expected Interfaces

None new.

## Expected Functions

- `CompanionExperienceEngine.check_for_greeting(idle_duration_seconds: float) -> CompanionMoment | None` — never raises; returns `None` below `greeting_idle_threshold_seconds`, otherwise a `GREETING` moment (with `referenced_content=None` unless `check_for_continuity_callback()` — called internally as a secondary check — finds something worth folding in, in which case a single combined `GREETING` moment carries both, avoiding two separate, back-to-back companion-experience moments firing on the same session start).
- `CompanionExperienceEngine.check_for_celebration() -> CompanionMoment | None` — never raises; queries `EmotionalMemory.recall_recent_moments()` (5.3) filtered further to `emotional_significance >= celebration_significance_threshold`, and `EventMemory`'s own existing milestone records, preferring the more recent of the two if both qualify; returns `None` when neither does — an honest "nothing to celebrate right now" is the expected common case, not a failure.
- `CompanionExperienceEngine.check_for_continuity_callback() -> CompanionMoment | None` — never raises; a lighter-weight version of `check_for_celebration()` using `EmotionalMemory.recall_recent_moments()` at its own ordinary (not celebration-raised) threshold, for the "last time we talked you mentioned X" case that doesn't need to be a standout moment, just a genuine, real one.

## Data Flow

```
(at session start, real trigger wired at Sprint 5.14)
        |
        v
CompanionExperienceEngine.check_for_greeting(idle_duration_seconds)
        |
        +--> (internally) check_for_continuity_callback() -> CompanionMoment | None
        |
        v
   CompanionMoment | None
        |
        v
   (consumed by Sprint 5.14's real wiring: folded into the greeting reply's own
    content input, phrased through Persona.compose_reply(), NOT built here)


(separately, at any point a real trigger decides to check — Sprint 5.14's job)
CompanionExperienceEngine.check_for_celebration() -> CompanionMoment | None
        |
        v
   GestureEngine.trigger_event(GestureTrigger.NOTIFICATION, persona_name)  (5.9, existing)
        |
        v
   (a celebratory gesture, dispatched through PresentationController, unchanged
    from Sprint 5.9's own existing mechanism)
```

## Implementation Tasks

1. `config/schema.py`/`config/defaults.yaml` — new `PresentationConfig` thresholds.
2. `presentation/companion_experience.py` — `CompanionMomentType`, `CompanionMoment`, `CompanionExperienceEngine`.
3. `tests/unit/presentation/test_companion_experience.py` — greeting threshold behavior (below/at/above); celebration threshold behavior and `EmotionalMemory`-vs-`EventMemory` preference ordering; continuity-callback behavior; the combined-greeting-plus-continuity-callback case (no double-firing).

## Architecture Notes

This sprint's own class holds **no reference to any `Persona`, `Renderer`, or `TextToSpeech`** — consistent with `GestureEngine`'s (5.9) own established "decide the moment, not the phrasing/rendering" boundary. `CompanionMoment.referenced_content` is deliberately a plain string (the stored `MemoryRecord.content` verbatim), never a pre-formatted greeting sentence — turning it into natural language is `Persona.compose_reply()`'s own job (a template variant consuming `CompanionMoment` as new input, wired at Sprint 5.14), keeping this sprint's own class free of any user-facing phrasing decisions, the same Single-Responsibility boundary this Level has applied consistently since Sprint 5.4.

## Integration Considerations

- **No live caller until Sprint 5.14** — session-start/idle-duration detection, and the real decision of *when* to check for a celebration (once per session? once per idle-to-active transition?) are that sprint's own design calls, not decided here.
- **A `WELLNESS`-shaped `CompanionMomentType` is deliberately NOT added this sprint** — the brief's own "Wellness reminders" item belongs entirely to Part B's future Wellness Engine (sprints 5.17–5.19); this sprint's `CompanionMomentType` enum is left extensible (a plain `Enum`, trivially extended later) but is not pre-populated with a value nothing in Part A produces or consumes, avoiding the same "reserved but never wired" confusion this project has occasionally had to correct after the fact (e.g. `backlog/technical_debt.md` item 17's own history) — when Part B is written, it makes this decision explicitly rather than inheriting an unused placeholder from Part A.

## Potential Risks

- **Greeting/celebration thresholds are unvalidated, disclosed defaults**, the same category as every other tuned constant in this Sprint Book.
- **A celebration or continuity callback referencing something the user might have wanted forgotten is a real, if narrow, privacy consideration** — mitigated structurally by relying entirely on `MemoryLifecycleManager`'s own existing deletion/cleanup passes (Sprint 3.6): a record that's been deleted or has decayed out of `EmotionalMemory.recall_recent_moments()`'s own significance threshold simply can't be surfaced here, since this class never bypasses that existing lifecycle — no new privacy surface is introduced, only a new *reader* of an already-governed store.

## Acceptance Criteria

- All three `check_for_*` methods never raise, including when both `EmotionalMemory`/`EventMemory` are empty.
- Threshold behavior verified directly at, below, and above each configured boundary.
- The combined greeting-plus-continuity-callback case never produces two separate moments for one session start.
- `ruff check .` clean; full existing suite unaffected.

## Testing Checklist

- [ ] Unit: `check_for_greeting()` threshold and combined-moment behavior.
- [ ] Unit: `check_for_celebration()` threshold and source-preference ordering.
- [ ] Unit: `check_for_continuity_callback()` behavior against a real `EmotionalMemory` fixture.
- [ ] Full regression: existing suite unaffected.

## Documentation Checklist

- [ ] `presentation/companion_experience.py` docstring explains the "decide the moment, not the phrasing" boundary and explicitly states that Wellness reminders are out of this sprint's own scope (Part B's job).
- [ ] `docs/STATUS.md` — Level 5 Part A row updated.

## Definition of Done

Per `docs/CODING_STANDARDS.md`.

## Estimated Complexity

Medium.

## Estimated Development Time

1.5–2 days.

## Risks

See Potential Risks above.

## Next Sprint

5.14 — Presentation Layer Integration.

## Future Considerations

- A `WELLNESS`-shaped `CompanionMoment` — real work for whichever Part B sprint first needs it (Integration Considerations above).
- Richer celebration content (not just referencing stored memory text verbatim, but a more elaborate framing) is real future content work, not architecture.
