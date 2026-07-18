# Sprint 3.11 — Authority Evaluation & Engine Selection

## Sprint ID

3.11

## Sprint Name

Authority Evaluation & Engine Selection

## Purpose

Implement the Decision Engine pipeline's final two stages, per [02_System_Architecture.md](../02_System_Architecture.md): *"... → Authority Evaluation → Engine Selection → Execution → Response Generation."* Closes Phase 3.3 (Decision Engine)'s acceptance criteria: *"Correct subsystem selected. Explainability preserved."* Implements Part 2's Authority System (three levels: Inform, Recommend, Emergency Assist) and produces the explainable decision trace the Explainability Rule requires.

## Engineering Rationale

Authority Evaluation and Engine Selection are combined in one sprint, as [sprint_book/INDEX.md](INDEX.md)'s original roadmap already proposed, because they are two judgments made from the exact same inputs at the exact same moment — splitting them would mean passing one freshly-computed context object through an artificial extra pipeline hop for no real separation-of-concerns benefit; [04_Master_Implementation_Plan.md](../04_Master_Implementation_Plan.md)'s own Phase 3.3 task list treats them as one unbroken sequence. This mirrors exactly how Sprint 2.11 combined "Persona Switching" and "Explicit Selection" into one sprint rather than two.

Phase 3.3's own acceptance criterion is "Explainability preserved" — not a separate, later sprint. This sprint therefore builds explainability as a **first-class deliverable**, not an afterthought bolted onto the decision output: every evaluation produces a `DecisionTrace` capturing every input that fed the decision (intent, context analysis, retrieved memories with their own `retrieval_reason` from Sprint 3.9, priority level) and a `reasoning_text` that directly answers the Explainability Rule's own worded test — *"the user may ask: Why? JARMINEI should always provide the reasoning behind its behavior."*

Part 2's Authority System is narrow by design: *"Level 3 (Emergency Assist): Execute previously approved emergency procedures... Emergency actions never include: deleting files, sending messages, purchasing, installing software, sharing information — those always require approval."* At this point in the roadmap, **zero emergency procedures are pre-approved anywhere in the codebase** — Device Control (Level 4) doesn't exist yet, so there is nothing for `EMERGENCY_ASSIST` to actually execute. This sprint makes that limitation structural, not accidental: `AuthorityEvaluator` maintains a whitelist of pre-approved procedure identifiers (empty at Level 3), and can only ever select `EMERGENCY_ASSIST` for a procedure that appears on it — a default-deny design, not a default-allow one guarded by exclusions. In practice, at Level 3, every `EMERGENCY_ASSIST`-classified request degrades to `RECOMMEND` (inform and strongly suggest, never auto-execute), which is the honest, correct behavior for a system with no approved actions yet, not a bug to fix later. This is recorded here explicitly so it is understood as designed-in scope, exactly like `SwitchReason.CRITICAL_EMERGENCY` being "reserved" in Sprint 2.11.

Similarly, "Engine Selection" at Level 3 has only two real destinations to select between — Level 4+ engines (Device Control, Workflow, Scheduler, Internet Agent) and Level 5+ engines (Emotion, Wellness, Analytics, Learning) do not exist yet. This sprint's `EngineSelection` enum names all of them (matching Part 2's full architecture), but only `CONVERSATIONAL_RESPONSE` and `INFORM_ONLY` have a real handler at Level 3 — every other value is reserved, exactly like `IntentCategory`/`SwitchReason`/`PriorityLevel` before it. Selecting a reserved engine is itself always downgraded to `CONVERSATIONAL_RESPONSE` with the limitation stated plainly in `reasoning_text` (e.g. *"this looks like a task for Device Control, which doesn't exist yet — here's what I can tell you instead"*) — an honest degrade, not a silent failure, per Human First and Reliability over Intelligence.

## Objectives

- An `AuthorityEvaluator` that, given Intent (3.7), Context Analysis (3.8), retrieved memories (3.9), and priority (3.10), determines an `AuthorityLevel` and an `EngineSelection`.
- A `DecisionTrace` capturing every input and a human-readable `reasoning_text`, queryable via `explain()`.
- A structural, whitelist-based (default-deny) guarantee that `EMERGENCY_ASSIST` can never select an unapproved action — currently an empty whitelist, so it never fires at Level 3.
- Selecting a not-yet-real `EngineSelection` value always degrades to `CONVERSATIONAL_RESPONSE`, with the limitation stated in `reasoning_text`.

## Dependencies

3.7 (Intent Detection), 3.8 (Context Analysis), 3.9 (Memory Retrieval Engine), 3.10 (Priority Queue)

## Files to Create

- `decision/authority.py` — `AuthorityLevel` (Enum), `EngineSelection` (Enum), `DecisionTrace` (dataclass), `AuthorityEvaluator(ManagedModule)`.
- `tests/unit/decision/test_authority.py`

## Files to Modify

None.

## Expected Classes

- `AuthorityLevel` (Enum) — `INFORM = 1`, `RECOMMEND = 2`, `EMERGENCY_ASSIST = 3`, matching Part 2's three levels and their exact numbering.
- `EngineSelection` (Enum) — `CONVERSATIONAL_RESPONSE` (wired), `INFORM_ONLY` (wired), `DEVICE_CONTROL` (reserved, Level 4), `WORKFLOW` (reserved, Level 4), `SCHEDULER` (reserved, Level 4), `INTERNET_AGENT` (reserved, Level 4), `WELLNESS` (reserved, Level 5), `EMOTION_SUPPORT` (reserved, Level 5). Every reserved value exists so future Levels only need to add a real handler, not modify this enum.
- `DecisionTrace` (dataclass) — `intent: Intent`, `context_analysis: ContextAnalysis`, `retrieved_memories: list[RetrievedMemory]`, `priority_level: PriorityLevel`, `authority_level: AuthorityLevel`, `selected_engine: EngineSelection`, `reasoning_text: str`, `decided_at: datetime`.
- `AuthorityEvaluator(ManagedModule)` — constructor DI: `(approved_emergency_procedures: frozenset[str] = frozenset())` (empty by default at Level 3 — see Engineering Rationale; the parameter exists now so Level 4 can inject real procedure ids without changing this class's signature).

## Expected Interfaces

- `ManagedModule` (reused) — `start()`/`stop()` log only; `health_check()` confirms the whitelist invariant still holds (a defensive check: `approved_emergency_procedures` being non-empty with no Device Control registered anywhere would itself indicate a configuration error at Level 3 — logged as a warning, not a hard failure, since Level 4+ genuinely will populate this).

## Expected Functions

- `AuthorityEvaluator.evaluate(intent: Intent, context_analysis: ContextAnalysis, retrieved_memories: list[RetrievedMemory], priority_level: PriorityLevel) -> DecisionTrace` — the single entry point. Determines `authority_level`: `EMERGENCY_ASSIST` only if `priority_level == CRITICAL_EMERGENCY` **and** a matching procedure id is found in `approved_emergency_procedures` (always false at Level 3, by design); otherwise `RECOMMEND` for `ACTION_REQUEST`/`EMERGENCY`-without-approval intents, `INFORM` for everything else. Determines `selected_engine`: `CONVERSATIONAL_RESPONSE` for anything persona-appropriate (the default), `INFORM_ONLY` for a pure informational answer with no persona reply needed; any other named engine that would be the "correct" future destination (inferred from `intent.category`/`context_analysis.primary_topic` for logging purposes only) is recorded in `reasoning_text` but always resolved to `CONVERSATIONAL_RESPONSE` as the actual `selected_engine`, since no other handler exists. Builds `reasoning_text` from every input, in plain language.
- `AuthorityEvaluator.explain(trace: DecisionTrace) -> str` — renders `trace.reasoning_text` (already human-readable) together with a short structured summary of `retrieved_memories`' `retrieval_reason`s — this is the literal function a future "why?" query (voice-triggered or Debug Console-triggered) would call; not wired to a live trigger in this sprint (see Integration Considerations).

## Data Flow

```
Intent (3.7) + ContextAnalysis (3.8) + list[RetrievedMemory] (3.9) + PriorityLevel (3.10)
      ↓
AuthorityEvaluator.evaluate(...)
      ↓
authority_level = f(priority_level, approved_emergency_procedures, intent.category)
selected_engine = f(intent.category, context_analysis.primary_topic) → always CONVERSATIONAL_RESPONSE or INFORM_ONLY at Level 3
reasoning_text = human-readable justification of both
      ↓
DecisionTrace(...)
      ↓
Sprint 3.12's Decision Engine Integration → Persona.compose_reply(transcript, context, decision_trace)
      ↓
AuthorityEvaluator.explain(trace) → (future) "why?" query surface
```

## Implementation Tasks

1. `decision/authority.py` — `AuthorityLevel`, `EngineSelection`, `DecisionTrace`, `AuthorityEvaluator(ManagedModule)`.
2. `evaluate()` — authority-level logic (whitelist-gated `EMERGENCY_ASSIST`), engine-selection logic (always-degrades-to-wired-value), `reasoning_text` construction.
3. `explain()` — trace rendering.
4. Unit tests, including the whitelist-gate defensive test (an `EMERGENCY_ASSIST`-priority item with an empty whitelist must never produce `AuthorityLevel.EMERGENCY_ASSIST`) and the engine-degrade test (a reserved `EngineSelection` inference always resolves to `CONVERSATIONAL_RESPONSE` in the actual returned trace).

## Architecture Notes

This sprint closes **Phase 3.3 (Decision Engine)**. Combined with Sprints 3.7–3.10, the full pipeline from Part 2's diagram now exists end-to-end as real, connected code: Intent Detection → Context Analysis → Memory Retrieval → Priority Evaluation → Authority Evaluation → Engine Selection. "Execution" and "Response Generation" (the diagram's final two steps) are **not** built by this sprint — at Level 3, "execution" of a `CONVERSATIONAL_RESPONSE` selection *is* `Persona.compose_reply()` (already built, Sprint 2.9/2.10), now finally receiving real decision input instead of a placeholder; there is no separate Level 3 "Execution Engine" to build, since nothing exists yet for it to execute beyond conversation. This is stated explicitly so the pipeline diagram's last two boxes aren't mistaken for missing scope — they resolve to existing Level 2 machinery, wired properly in Sprint 3.12.

## Integration Considerations

- No live caller exists yet — Sprint 3.12 is the first to call `evaluate()` in the real turn-processing path and pass its `DecisionTrace` into `Persona.compose_reply()`'s new parameter (`personas/base.py`'s own docstring already anticipated this: *"the anticipated (not yet added) extra parameter flagged in [Sprint 2.9's] Risks"*).
- `explain()` has no live trigger yet (no "why did you say that" voice command, no Debug Console panel) — Level 3's goal list requires explainability to *exist and be preserved*, not to be voice-queryable; a real trigger is flagged as a Future Consideration.
- Level 4's Device Control sprint (4.1+) is the first real candidate to populate `approved_emergency_procedures` with actual pre-approved procedure ids — this sprint's constructor parameter exists specifically so that requires no change to `AuthorityEvaluator` itself, only to what `main.py`'s composition root passes in.

## Potential Risks

- **An empty `approved_emergency_procedures` whitelist means `EMERGENCY_ASSIST` is structurally unreachable at Level 3** — this is correct, honest behavior (see Engineering Rationale), but must not be mistaken for a bug during Sprint 3.14's acceptance testing; the acceptance criteria for this sprint explicitly test *for* this unreachability, not around it.
- **`selected_engine`'s "inferred correct future engine" logic (used only for `reasoning_text`, never for the actual returned value) risks looking like real routing intelligence that doesn't exist yet** — must be worded carefully in `reasoning_text` to be honest about the gap ("this looks like X, which isn't available yet") rather than implying real capability.
- **`DecisionTrace` growing large** (it embeds full `Intent`/`ContextAnalysis`/`RetrievedMemory` objects) — acceptable for Level 3's request volume and in-memory use; persisting every trace long-term is explicitly out of this sprint's scope (no `DecisionTrace` table is created here — see Future Considerations).

## Acceptance Criteria

- No input combination can produce `AuthorityLevel.EMERGENCY_ASSIST` while `approved_emergency_procedures` is empty (defensive, exhaustive over `priority_level`/`intent.category` combinations).
- `selected_engine` in the returned `DecisionTrace` is always `CONVERSATIONAL_RESPONSE` or `INFORM_ONLY` at Level 3, regardless of what `reasoning_text` says would ideally handle the request.
- `reasoning_text` is non-empty and references at least the `intent.category` and `priority_level` that led to the decision, for every evaluated case.
- `explain(trace)` includes every `retrieval_reason` from `trace.retrieved_memories`.
- Combined with Sprints 3.7–3.10, Phase 3.3's Acceptance Criteria ("Correct subsystem selected. Explainability preserved.") are met.

## Testing Checklist

- [ ] Unit: whitelist-gate defensive test (empty whitelist ⇒ `EMERGENCY_ASSIST` unreachable, exhaustive over inputs).
- [ ] Unit: a non-empty whitelist with a matching procedure id *does* allow `EMERGENCY_ASSIST` (proves the gate isn't hardcoded shut, only correctly empty by default).
- [ ] Unit: engine-selection degrade test (reserved-engine inference never appears as the actual `selected_engine`).
- [ ] Unit: `reasoning_text` content correctness across a fixed set of representative inputs.
- [ ] Unit: `explain()` includes all `retrieval_reason`s.
- [ ] Unit: `health_check()` warns (not fails) if the whitelist is non-empty with no real caller — best-effort defensive check.

## Documentation Checklist

- [ ] `decision/authority.py` docstring: full Authority Level / Engine Selection tables with wired/reserved status, explicit statement that `EMERGENCY_ASSIST` is structurally unreachable at Level 3 by design, cross-referencing Level 4 (Device Control) as where the whitelist gets populated.
- [ ] `docs/STATUS.md` — Phase 3.3 (Decision Engine) marked **Complete**.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md). This sprint also closes Phase 3.3 (Decision Engine) and, in combination with Sprints 3.1–3.10, all of Level 3's individual-component sprints — the same milestone `sprint_2_11.md` reached for Level 2 before its own integration/hardening/freeze sprints.

## Estimated Complexity

High — the whitelist-gated authority logic and the engine-selection degrade path both have more edge cases than their line count suggests, and getting the `reasoning_text` genuinely explainable (not just present) is real, non-mechanical work.

## Estimated Development Time

2–2.5 days.

## Next Sprint

3.12 — Decision Engine Integration.

## Future Considerations

- Persisting `DecisionTrace` history (for a real "what did you decide yesterday and why" query) is a plausible future `memory/` or `database/` extension — not built now, since nothing in Level 3's goal list requires trace *persistence*, only trace *existence* per-decision.
- A real "why?" voice trigger surfacing `explain()` — flagged as a natural, low-risk addition once Sprint 3.12 wires the rest of the pipeline live; not required by this sprint's own Acceptance Criteria.
- Level 4's Device Control sprint (4.1) should treat populating `approved_emergency_procedures` as a deliberate, reviewed act — per Part 2's own "those always require approval" language, this whitelist is exactly the enforcement point that promise depends on.

---

## Sprint Completion Report (2026-07-18)

### Summary

Implemented `decision/authority.py` (`AuthorityLevel`, `EngineSelection`, `DecisionTrace`, `AuthorityEvaluator`). No files modified. This closes **Phase 3.3 (Decision Engine)** and, combined with Sprints 3.1–3.6, **all of Level 3's individual-component sprints (3.1–3.11)**. 571/571 tests passing (512 prior + 59 new), `ruff check .` clean.

### Files Created

- `decision/authority.py` — `AuthorityLevel` (Enum), `EngineSelection` (Enum), `DecisionTrace` (dataclass), `AuthorityEvaluator`.
- `tests/unit/decision/test_authority.py` — 59 tests (including an exhaustive `itertools.product(PriorityLevel, IntentCategory)` parametrization — 35 cases — for the whitelist-gate defensive test).

### Files Modified

- `docs/STATUS.md` — Phase 3.3 (Decision Engine) marked **Complete**.

### Tests Added

59 total, all against plain constructed `Intent`/`ContextAnalysis`/`RetrievedMemory` fixtures (no fakes needed — `AuthorityEvaluator` has no external I/O dependency at all). Covers: the exhaustive empty-whitelist-makes-`EMERGENCY_ASSIST`-unreachable test across every `PriorityLevel`×`IntentCategory` combination (35 cases); a non-empty whitelist *with* a matching procedure id correctly allowing `EMERGENCY_ASSIST`, and *without* a match still correctly falling back to `RECOMMEND`; `ACTION_REQUEST`→`RECOMMEND` and every other category→`INFORM`; the engine-selection degrade path proving `ACTION_REQUEST`/`EMOTIONAL_SUPPORT` never actually select their "ideal" reserved engine (`DEVICE_CONTROL`/`WELLNESS`) even though `reasoning_text` names the gap honestly; `INFORMATIONAL`→`INFORM_ONLY`; `reasoning_text` referencing both `intent.category` and `priority_level` by name across four representative cases, plus the retrieved-memory-count mention and the honest unapproved-emergency wording; `explain()` including every `retrieval_reason` verbatim and stating plainly when no memories were retrieved; `health_check()` returning `True` regardless of whitelist state, with a real `caplog`-verified warning only when non-empty; and `DecisionTrace` carrying every input it was constructed from unchanged.

### Documentation Updated

This file (Sprint Completion Report). `decision/authority.py`'s module docstring (full Authority Level / Engine Selection tables with wired/reserved status, the structural-unreachability rationale for `EMERGENCY_ASSIST`, and the procedure-id-derivation decision below). `docs/STATUS.md` as above.

### Acceptance Criteria Checklist

- ✔ No input combination produces `AuthorityLevel.EMERGENCY_ASSIST` while `approved_emergency_procedures` is empty — proven exhaustively, not just spot-checked.
- ✔ `selected_engine` in the returned `DecisionTrace` is always `CONVERSATIONAL_RESPONSE` or `INFORM_ONLY` at Level 3, verified across every `IntentCategory`.
- ✔ `reasoning_text` is non-empty and references both `intent.category` and `priority_level` by name, for every evaluated case checked.
- ✔ `explain(trace)` includes every `retrieval_reason` from `trace.retrieved_memories`.
- ✔ Combined with Sprints 3.7–3.10, Phase 3.3's Acceptance Criteria ("Correct subsystem selected. Explainability preserved.") are met — confirmed with a real, non-mocked run of the entire pipeline together (see Remaining Risks).

### Engineering Decisions

- **The emergency whitelist is checked against a normalized `ContextAnalysis.primary_topic`** (`.strip().lower()`), not a dedicated procedure-id parameter — `evaluate()`'s own spec'd signature (`intent, context_analysis, retrieved_memories, priority_level`) has no such parameter, and `primary_topic` is the only available description of what the request is about. This is a genuine implementation-time decision the spec's own prose ("a matching procedure id is found") didn't resolve concretely — harmless at Level 3 since the whitelist is always empty regardless of what string is checked, but Level 4 (Device Control) should be aware of this exact matching mechanism when it actually populates the whitelist with real procedure ids, so topic phrasing and procedure ids can be kept in agreement.
- **`selected_engine` maps directly off `intent.category`, not `authority_level`**: `INFORMATIONAL` → `INFORM_ONLY`, every other category → `CONVERSATIONAL_RESPONSE` (including `CASUAL_CONVERSATION`/`EMOTIONAL_SUPPORT`/`MEMORY_RECALL`/`UNKNOWN`, which all resolve to `AuthorityLevel.INFORM` but clearly still want persona-flavored replies, not a bare fact). Tying `INFORM_ONLY` to `authority_level == INFORM` broadly would have wrongly stripped personality from a casual chat or an emotional-support reply.
- **`_INFERRED_FUTURE_ENGINE` only names `ACTION_REQUEST`→`DEVICE_CONTROL` and `EMOTIONAL_SUPPORT`→`WELLNESS`** — every other category is already correctly served by `CONVERSATIONAL_RESPONSE`/`INFORM_ONLY` at Level 3, so naming a "future engine gap" for them would be dishonest (there is no gap to name). Kept as a small, explicit, easily-extended dict rather than inferring anything more elaborate from `context_analysis.primary_topic`, since only `intent.category` was actually needed to make the two real gaps explicit.
- **`health_check()` always returns `True`**, per the spec's own explicit "logged as a warning, not a hard failure" instruction — a non-empty whitelist at Level 3 is unusual (nothing yet is meant to populate it) but not itself evidence of a broken system, since Level 4+ genuinely will populate this exact field.

### Remaining Risks

- **Confirmed via a real, non-mocked run of the ENTIRE Level 3 Decision Engine pipeline together** (Sprints 3.7–3.11 in one script, not just this sprint's own unit tests) — real `OllamaClient` (llama3) → real `IntentDetector`/`ContextAnalyzer` → real `MemoryRetrievalEngine` against a real SQLite+Chroma `MemoryStore` → real `PriorityQueueManager` → real `AuthorityEvaluator`, across three genuinely different real transcripts (a technical bug-fix request, a factual question, and an emergency phrase). All three produced correct, sensible results end-to-end: the bug-fix request classified `ACTION_REQUEST`→`RECOMMEND`→`CONVERSATIONAL_RESPONSE` with an honest "Device Control doesn't exist yet" note and a correctly-recalled relevant memory; the factual question classified `INFORMATIONAL`→`INFORM`→`INFORM_ONLY`; the emergency phrase classified `EMERGENCY`→`CRITICAL_EMERGENCY` priority→`RECOMMEND` authority (correctly NOT `EMERGENCY_ASSIST`, since the whitelist is empty) with the exact honest "no pre-approved emergency procedures" wording this sprint's own spec called for. This exceeds this sprint's own committed scope (a full real-pipeline run wasn't required by the Testing Checklist) but directly closes Phase 3.3's own combined acceptance criterion, which no single sprint's isolated tests could fully demonstrate alone.
- This sprint's own flagged risks stand as expected and by design, not as open bugs: `EMERGENCY_ASSIST` is structurally unreachable at Level 3 (verified exhaustively above, matching the sprint's own acceptance criteria "testing *for* this unreachability, not around it"); the "inferred future engine" wording in `reasoning_text` was written carefully to state a capability gap honestly rather than imply real routing intelligence; `DecisionTrace` embeds full nested objects but is not persisted anywhere (no new table), acceptable at Level 3's in-memory, per-decision usage.
- `backlog/technical_debt.md` item 16 (shipped `ollama_model` default vs. the actually-pulled local model) applies to this sprint's own real-pipeline verification the same way it applied to 3.7–3.9 — used `llama3` explicitly, not the shipped `"gemma3"` default.

### Technical Debt

None new.

### Recommendations

- **For Sprint 3.12 (Decision Engine Integration)**: wires `evaluate()` into the real turn-processing path and passes its `DecisionTrace` into `Persona.compose_reply()`'s new parameter — `personas/base.py`'s own docstring already anticipated this exact parameter. Also the first sprint to populate `main.py`'s composition root with real `IntentDetector`/`ContextAnalyzer`/`MemoryRetrievalEngine`/`PriorityQueueManager`/`AuthorityEvaluator` instances, mirroring how Sprint 2.12 was the first to wire Level 2's individually-built modules together.
- **For Level 4's Device Control sprint (4.1)**: when populating `approved_emergency_procedures` for real, keep procedure ids in the same normalized form (`ContextAnalysis.primary_topic.strip().lower()`) that `AuthorityEvaluator._determine_authority()` checks against — see this sprint's own Engineering Decisions for why that specific matching mechanism was chosen.
- **This closes all of Level 3's individual-component sprints (3.1–3.11)** — per this project's own established pattern (Sprint 2.14 mirroring Sprint 1.9's acceptance-pass discipline), Level 3 likely wants its own integration/hardening/freeze sequence next (Sprint 3.12 Decision Engine Integration is already named as such; 3.13/3.14 presumably mirror 2.13/2.14's hardening-then-freeze shape, per `sprint_book/INDEX.md`).

**Sprint 3.11 (Authority Evaluation & Engine Selection) is complete — Phase 3.3 (Decision Engine) is now `Complete`.** **This also closes all of Level 3's individual-component sprints (3.1–3.11).** **Sprint 3.12 (Decision Engine Integration) is next.**
