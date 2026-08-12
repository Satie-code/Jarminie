# Sprint 6.16 — Startup & Caching Optimization

## Sprint ID

6.16

## Sprint Name

Startup & Caching Optimization

## Purpose

Open Level 6 Part B (Stabilization) with Phase 6.1's own literal mandate: "Optimize startup. Reduce resource usage. Improve caching. Improve responsiveness." Against the real, complete Level 1–6 Part A system (frozen at Sprint 6.15), not a hypothetical one.

## Engineering Rationale

This is **not** a green-field performance sprint. A separate, already-complete 10-phase "Runtime Refactor" workstream (2026-08-08, authorized directly by the user outside the Sprint Book process and tracked only in code docstrings — `core/manager.py`, `core/module_registry.py`, `core/runtime_manager.py`, and ~17 other files each carrying a `Runtime Phase N (Runtime Refactor Sprint)`-tagged docstring, per this project's own established convention for that one workstream) already did the large-scale lazy-loading rearchitecture this Phase's own name implies: a `ServiceTier`/`RuntimeManager` system (Phase 2), background-thread Tier B/C startup so only Tier A blocks `main()` (Phase 4), `LazyModule` treatment for Whisper/Coqui TTS/`MemoryStore` (Phases 5–6), idle-service eviction (`sweep_idle_services()`/`evict_least_recently_used()`, Phase 9), and a read-only diagnostics window (`ui/runtime_diagnostics_panel.py`, Phase 10). **This sprint's real job is auditing what that refactor left unfinished and adding the one category of work it never touched at all: a real, regression-guarding performance baseline** — no test anywhere in this codebase currently asserts a startup-time or resource-usage bound; every one of this project's own "host-load `wait_for_dormant`-class flake" entries in `backlog/technical_debt.md` is indirect evidence that startup/resource cost is being watched informally (via flaky test symptoms) rather than measured directly.

**First disclosed decision**: the Runtime Refactor's own 10 phases are formally cross-referenced into `docs/STATUS.md` as part of this sprint's own Documentation Checklist, not left permanently undocumented outside code — the natural point to do so, since this sprint is the first to build additional startup/caching work directly on top of it and needs the prior art named, not silently assumed.

## Objectives

- Defer `memory/chroma_client.py`'s `import chromadb` (currently a module-top-level import, `memory/chroma_client.py:15`, pulled in transitively at process start via `main.py`'s own top-level `from memory.chroma_client import ChromaMemoryClient`) to inside `ChromaMemoryClient.connect()` — the Runtime Refactor's own Phase 6 already deferred the `PersistentClient` *connection* (`MemoryStore` is `tier=WARM, lazy=True`), but the `import chromadb` statement's own cost (ChromaDB plus its bundled `onnxruntime` embedding machinery) is still paid eagerly at every startup regardless, a real gap that refactor never closed.
- Audit the ~17 `tier=WARM`-but-eager modules (`main.py`'s `_register_level*_modules()` functions) for genuine lazy-load candidates beyond the three (`STT`, `TTS`, `MemoryStore`) already marked `lazy=True` — apply `lazy=True` only where a module's own `start()` does real, deferrable work (a model load, a network probe), not where it's already cheap in-memory construction (the Runtime Refactor's own Phase 7 rationale for leaving most of them eager).
- Investigate `context/context_engine.py`'s `ContextEngine.build()` (composes five collaborators — `ContextManager`, `MemoryStore`, `UsageStore`, `CalendarStore`, `ResourceMonitor` — on every call) as the leading caching candidate: confirm whether it is genuinely called more than once within a single turn/tick window (by `AdaptivePrioritizer`, `ProactiveAssistant`, `ReasoningEngine`, or `_handle_planning_turn()`/`_handle_explanation_turn()` together) before adding a short-TTL memoization — per this project's own "don't harden/optimize speculatively" discipline, add a cache only if a real duplicate-call pattern is confirmed, not because the shape looks cacheable.
- Add `tests/system/test_startup_performance.py` — a real, regression-guarding baseline: measures Tier A startup wall-clock time and post-full-startup RSS against a documented, generous threshold (matching this project's own established tolerance for real-machine variability — the same reasoning behind the already-documented host-load flake class, not a CI-grade tight bound, since no CI exists).

## Dependencies

1.1–6.15 (the complete, frozen Level 1–6 Part A system) plus the Runtime Refactor workstream (2026-08-08, prior art this sprint extends, not a numbered Sprint Book dependency but a real prerequisite).

## Files to Create

- `tests/system/test_startup_performance.py`

## Files to Modify

- `memory/chroma_client.py` (deferred `import chromadb`)
- `main.py` (any `lazy=True` reclassifications the audit confirms; the Runtime Refactor's own prior-art comment block gains a note pointing at this sprint as its own continuation)
- `context/context_engine.py` (only if the duplicate-call investigation confirms a real caching candidate)
- `docs/STATUS.md` (Runtime Refactor cross-reference, per Engineering Rationale)

## Expected Classes

None new, unless the `ContextEngine.build()` investigation confirms a real caching candidate, in which case a small internal cache (a plain dict keyed on a cache-window timestamp, not a new public class).

## Expected Functions

None new — this sprint adjusts import placement, `lazy=True` classification, and (conditionally) adds a private memoization layer to an existing method.

## Data Flow

Unchanged — this sprint changes *when* work happens (import time vs. first use, computed vs. cached), never *what* any existing flow produces.

## Implementation Tasks

1. Move `import chromadb` from `memory/chroma_client.py`'s module top level into `ChromaMemoryClient.connect()`; confirm via a real, timed `import main` (or equivalent) that process-start import cost drops, and that `MemoryStore`'s own already-lazy `connect()` behavior is otherwise unchanged.
2. Audit `main.py`'s `_register_level2_modules()` through `_register_level6_part_a_modules()` for `tier=WARM`-but-eager candidates; reclassify only where a module's own `start()` does real, deferrable work, each reclassification justified in this sprint's own eventual completion report the same way Sprint 6.1–6.15's own each disclosed their design calls.
3. Investigate `ContextEngine.build()`'s real call frequency within one turn/tick (repo-wide call-site trace, not assumption); add a short-TTL cache only if confirmed genuinely duplicated.
4. `tests/system/test_startup_performance.py`: real Tier A startup timing (wrap `CoreManager.startup_tier(ServiceTier.CRITICAL)` or equivalent) and post-startup RSS (`psutil.Process().memory_info().rss`), asserted against a documented, generous threshold; skip/xfail gracefully (not a hard failure) under detected extreme host load, mirroring this project's own already-established `wait_for_dormant`-class tolerance rather than inventing a stricter new standard this one test alone would enforce.
5. `docs/STATUS.md` — new subsection cross-referencing the Runtime Refactor's own 10 phases as prior art, immediately followed by this sprint's own narrative once implemented.

## Architecture Notes

This sprint does not re-architect the lazy-loading system the Runtime Refactor already built — `ServiceTier`, `RuntimeManager`, `LazyModule` all stay exactly as they are. Its own scope is narrowly: close the one real gap that system left open (an eagerly-imported heavy dependency inside an otherwise-lazy module), and add the measurement discipline that never existed for any of it.

## Integration Considerations

- Sprint 6.18 (Stress & Recovery Testing) reuses this sprint's own RSS-measurement approach as its own resource-growth-over-time baseline.
- Sprint 6.23 (Full Test Suite Pass) extends this sprint's own single-point startup measurement into a sustained resource test, per the locked spec's own "Resource tests" Final Testing category.

## Potential Risks

- **The `ContextEngine.build()` duplicate-call investigation may find no real repeated-call pattern** — in which case no cache is added, a legitimate "confirmed unnecessary" outcome, not a failure to deliver a caching improvement, matching this project's own "don't harden/optimize speculatively" discipline applied to performance work for the first time.
- **A startup-time/RSS threshold generous enough to survive real host-load variability may be too loose to catch a genuine future regression** — disclosed explicitly rather than tuned to a false precision this project's own hardware has never actually demonstrated it can hold to.

## Acceptance Criteria

- `import chromadb`'s own cost no longer occurs at process start; a real, timed comparison shows a measurable reduction.
- Every `lazy=True` reclassification (if any) preserves its module's own existing Acceptance Criteria from its original owning sprint — verified by that module's own pre-existing test suite continuing to pass unchanged.
- `tests/system/test_startup_performance.py` passes against the real, complete system and fails honestly (not silently) if a future change regresses startup time/RSS beyond the documented threshold.
- Full test suite (unit + integration + system, opt-in real-model marker excluded) passes with zero regressions.
- `ruff check .` clean.

## Testing Checklist

- [ ] Real, timed `import chromadb` deferral confirmation.
- [ ] Full existing Level 1–6 Part A suite re-run, confirmed unaffected by any `lazy=True` reclassification.
- [ ] `tests/system/test_startup_performance.py`.
- [ ] Full project suite re-run.

## Documentation Checklist

- [ ] `docs/STATUS.md` — Runtime Refactor cross-reference note, plus this sprint's own narrative once implemented.
- [ ] `docs/sprint_book/INDEX.md` — 6.16 row → `Complete` (once implemented).

## Definition of Done

Per [docs/CODING_STANDARDS.md](../../CODING_STANDARDS.md).

## Estimated Complexity

Medium.

## Estimated Development Time

1.5–2.5 days.

## Risks

See Potential Risks above.

## Next Sprint

6.17 — Async Background Task Audit.

## Future Considerations

- A genuine startup-time benchmark HISTORY (tracked numbers across releases, not just a single pass/fail threshold) would need a CI pipeline this project doesn't have (see Sprint 6.23's own Future Considerations) — out of scope here.
- If the `ContextEngine.build()` investigation finds a real duplicate-call pattern too large to fix safely within this sprint's own narrow scope, log it to `backlog/technical_debt.md` rather than force a rushed fix.
