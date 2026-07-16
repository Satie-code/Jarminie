# Sprint 2.6 — Quiet Mode Controller

## Sprint ID

2.6

## Sprint Name

Quiet Mode Controller

## Purpose

Implement Quiet Mode as its own explicit module, per [02_System_Architecture.md](../02_System_Architecture.md): *"Quiet Mode is the default operating state. JARMINEI remains dormant until: Wake phrase. Approved emergency. High-priority scheduled alert. This prevents unwanted interaction and unnecessary resource usage."* and [01_Project_Vision.md](../01_Project_Vision.md)'s Core Philosophy: *"Quiet Mode is the default operating state."* This sprint completes Phase 2.1 (Voice Pipeline) and its acceptance criteria: *"Wake phrase activates JARMINEI. Speech recognition functions. Voice responses function."*

## Engineering Rationale

Wake Word Detector (2.2) owns the *mechanism* of detecting a phrase; Microphone Manager (2.1) owns the *mechanism* of switching capture modes. Neither owns the *policy* of what those events mean at the system level — that policy is Quiet Mode itself, and giving it a dedicated module keeps Single Responsibility intact rather than letting dormant/active state logic leak into either lower-level module. This is also the natural place to make Part 2's full activation-priority list *representable*, even though only one of its four triggers has a real caller in Level 2:

1. Critical emergency — no Authority System exists yet (Level 3, Sprint 3.10); reserved, not wired.
2. Explicit user selection — not a Quiet Mode concern; this is Persona Switching (2.11), which operates *within* an already-active session.
3. Context detection — same as above; out of scope here.
4. Daily routine — no Scheduler exists yet (Level 4); reserved, not wired.

Only the wake-phrase trigger has a real source in Level 2. The other three activation reasons are defined in the `ActivationReason` enum now — because a state machine that can't even *name* the states Part 2 requires would need reshaping later — but each is explicitly documented as unwired, not implemented, per this task's constraint against introducing productivity/scheduling/authority functionality prematurely.

## Objectives

- A `QuietModeController` holding the single source of truth for `OperatingMode` (`DORMANT` / `ACTIVE`).
- Enforces the Microphone Rule structurally: the only path from `DORMANT` to `ACTIVE` is a successful wake-word detection (in Level 2); the only path back is a Voice Session Manager session-end event.
- Exposes an `activate(reason)` entry point shaped for future callers (Level 3 emergency, Level 4/5 scheduled alerts) without implementing what those callers will do.

## Dependencies

2.2 (Wake Word Detector), 2.5 (Voice Session Manager & Timeout)

## Files to Create

- `voice/quiet_mode.py` — `OperatingMode` (Enum), `ActivationReason` (Enum), `QuietModeController`.
- `tests/unit/voice/test_quiet_mode.py`

## Files to Modify

None — this sprint only wires existing callback seams (`WakeWordDetector.on_detected`, `VoiceSessionManager.on_session_ended`) together; it introduces no new config fields.

## Expected Classes

- `OperatingMode` (Enum) — `DORMANT`, `ACTIVE`.
- `ActivationReason` (Enum) — `WAKE_WORD`, `EXPLICIT_EMERGENCY` (reserved, Level 3), `SCHEDULED_ALERT` (reserved, Level 4/5). Ordered to mirror Part 2's stated priority (Critical emergency first) even though only `WAKE_WORD` has a caller.
- `QuietModeController(ManagedModule)` — constructor DI: `(session_manager: VoiceSessionManager)`. Registers itself as `WakeWordDetector`'s `on_detected` callback and `VoiceSessionManager`'s `on_session_ended` callback at `start()` — this wiring, not construction-time coupling, is what lets `QuietModeController` depend on `VoiceSessionManager` without `VoiceSessionManager` needing to know Quiet Mode exists.

## Expected Interfaces

- `ManagedModule` (reused) — `start()` attaches the callbacks; `stop()` detaches them; `health_check()` reports whether the controller's mode is consistent with the underlying session state (e.g. `ACTIVE` but no session actually running would indicate a bug, not a healthy state).

## Expected Functions

- `QuietModeController.activate(reason: ActivationReason) -> None` — transitions `DORMANT → ACTIVE`, calls `session_manager.begin_session()`. A no-op (logged) if already `ACTIVE` — cannot stack activations.
- `QuietModeController.deactivate() -> None` — transitions `ACTIVE → DORMANT`. Called internally when the wired `on_session_ended` callback fires.
- `QuietModeController.current_mode() -> OperatingMode`
- `QuietModeController._on_wake_word_detected(phrase: str) -> None` — internal: calls `activate(ActivationReason.WAKE_WORD)`.
- `QuietModeController._on_session_ended(reason: SessionEndReason) -> None` — internal: calls `deactivate()`.

## Data Flow

```
WakeWordDetector.on_detected(phrase)
      ↓
QuietModeController._on_wake_word_detected → activate(WAKE_WORD)
      ↓
OperatingMode: DORMANT → ACTIVE
      ↓
VoiceSessionManager.begin_session()
      ↓
   ... conversation turns ...
      ↓
VoiceSessionManager fires on_session_ended(reason)
      ↓
QuietModeController._on_session_ended → deactivate()
      ↓
OperatingMode: ACTIVE → DORMANT
```

## Acceptance Criteria

- JARMINEI starts in `DORMANT` mode.
- A wake-word detection transitions to `ACTIVE` and begins a voice session (verified against fakes for `WakeWordDetector`/`VoiceSessionManager`, not real hardware).
- A session ending (any `SessionEndReason`) transitions back to `DORMANT`.
- A second wake-word detection while already `ACTIVE` is ignored (logged), not treated as a new session — matches "only one session at a time."
- This sprint's completion satisfies Phase 2.1's full acceptance criteria in combination with 2.1–2.5.

## Testing Checklist

- [ ] Unit: starts in `DORMANT`.
- [ ] Unit: wake-word detection while `DORMANT` transitions to `ACTIVE` and calls `begin_session()`.
- [ ] Unit: wake-word detection while already `ACTIVE` is a no-op.
- [ ] Unit: session-end event transitions back to `DORMANT` regardless of `SessionEndReason` value.
- [ ] Unit: `health_check()` detects an inconsistent mode/session-state combination.

## Documentation Checklist

- [ ] `voice/quiet_mode.py` docstring: full activation-priority list from Part 2, explicitly marking which reasons are wired vs. reserved for later Levels.
- [ ] `docs/STATUS.md` — Phase 2.1 (Voice Pipeline) marked **Complete**: all four of its sprints (2.1–2.2, 2.3, 2.4, 2.5, 2.6) done, closing Phase 2.1's acceptance criteria per [04_Master_Implementation_Plan.md](../04_Master_Implementation_Plan.md).

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md). This sprint also closes Phase 2.1 (Voice Pipeline).

## Estimated Complexity

Medium — the state machine itself is small; getting the callback wiring direction right (who calls whom, and who must never know about whom) is the design discipline this sprint is really testing.

## Estimated Development Time

1 day.

## Risks

- **`EXPLICIT_EMERGENCY` and `SCHEDULED_ALERT` being unwired stubs** could be mistaken for "already handled" by a future sprint skimming this file — mitigated by the explicit Engineering Rationale wording above; re-confirm at Sprint 3.10 (Authority Evaluation) and Sprint 4.9 (Reminder Engine) that wiring them in doesn't require reshaping this enum.
- **No true interrupt path yet**: today, `activate()` while already `ACTIVE` is simply ignored. Once `EXPLICIT_EMERGENCY` is wired (Level 3), Part 2's rule that emergency "temporarily suspends the active persona" and resumes it afterward will need real suspend/resume semantics this sprint does not build — flagged here so it isn't a surprise at that Level, not something to solve now.

## Next Sprint

2.7 — Conversation Session Store.
