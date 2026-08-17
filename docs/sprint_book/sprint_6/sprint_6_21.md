# Sprint 6.21 — Privacy Verification

## Sprint ID

6.21

## Sprint Name

Privacy Verification

## Purpose

Close Phase 6.3's own remaining task, "Privacy verification" — confirm what data JARMINEI actually stores and what actually leaves the machine, against Part 2's own "Privacy protection" Security Layer responsibility and this project's own "local-first" default. Especially: Level 6 Part A's Knowledge Graph and Proactive Assistant, both new since Level 5 and neither previously audited from a privacy angle.

## Engineering Rationale

Research confirms one genuinely good-news finding and three real, disclosed gaps. **Good news, verified directly, not assumed**: every internet-search request (`internet/brave_search_provider.py`, `tavily_search_provider.py`, `searxng_search_provider.py`) sends only the current turn's own topic/transcript text (`voice/pipeline.py`'s own `query = trace.context_analysis.primary_topic.strip() or trace.intent.raw_transcript.strip()`) — never memory content, never conversation history, never knowledge-graph data. `proactive/proactive_assistant.py` reads local data only (`ContextEngine`, `KnowledgeGraphStore`) and its own output never leaves the process. **Three real gaps**: (1) `knowledge/knowledge_graph_store.py`'s `KnowledgeGraphStore` and `analytics/usage_store.py`'s `UsageStore` both have real, persistent, potentially-identifying data (project/person/topic entities; per-application usage samples) with **no retention or purge mechanism at all** — unlike `ConversationSessionStore`/`ActionAuditLog`/`MemoryStore`, all three of which already have a real `purge_older_than()`-style method wired to a genuine recurring `TaskScheduler` job (`backlog/technical_debt.md` items 11/15's own established, three-times-repeated resolution pattern). (2) `backlog/technical_debt.md` item 31's own explicit, never-resolved recommendation — *"Consider whether Sprint 4.18 or 4.19 should add an explicit `internet.enabled: bool` config flag to let a user disable outbound search entirely — a real, user-facing privacy control worth a deliberate decision"* — has sat open since Sprint 4.16 (2026-07-31) through every subsequent Level. (3) No "what do you know about me" / data-export / data-deletion surface exists anywhere — genuinely new conversational capability, not a hardening fix, disclosed rather than built here.

## Objectives

- `KnowledgeGraphStore.purge_older_than(cutoff)` — purges entities whose own `last_referenced_at` is older than a configured retention window, mirroring `ConversationSessionStore.purge_older_than()`'s own established shape, but with a real, disclosed difference: staleness-based (`last_referenced_at`), not blind creation-age, since a `PROJECT`/`PERSON` entity is a durable fact, not an ephemeral chat turn, and a much shorter default would silently discard genuinely still-relevant knowledge. New `KnowledgeGraphConfig.retention_days` (a generous default, e.g. 365).
- `UsageStore.purge_older_than(cutoff)` — purges raw per-poll `AppFocusSample` rows older than a configured window, mirroring the identical established pattern. New `AnalyticsConfig.sample_retention_days`.
- Both registered as new recurring `TaskScheduler` jobs in `voice/pipeline.py`'s `start()`, `resource_sensitive=True` (Sprint 6.19's own new classification, since neither has real user-facing lateness cost) — the fourth and fifth real instance of this exact "add the caller, register the job" resolution this project's own `backlog/technical_debt.md` items 11/15/24 already established three times over.
- New `InternetConfig.enabled: bool = True` (default preserves existing behavior) — `_handle_internet_agent_turn()` checks it before any outbound call, degrading to an honest "Internet research is currently turned off" reply rather than silently no-op-ing or crashing, closing `backlog/technical_debt.md` item 31's own long-open recommendation for real.
- Log (not build) the "what do you know about me" / data-export / data-deletion gap to `backlog/technical_debt.md` — a new item, the same treatment items 36/49 already gave genuinely new capability-shaped findings during an audit sprint.

## Dependencies

6.20 (shares the "what's actually stored/exposed" audit lens and the `resource_sensitive` job classification this sprint's own two new jobs use), Level 6 Part A's Knowledge Graph (6.6) and Proactive Assistant (6.8), 4.16–4.18 (Internet Agent).

## Files to Create

None expected.

## Files to Modify

- `knowledge/knowledge_graph_store.py` (`purge_older_than()`)
- `analytics/usage_store.py` (`purge_older_than()`)
- `config/schema.py` (`KnowledgeGraphConfig.retention_days`, `AnalyticsConfig.sample_retention_days`, `InternetConfig.enabled`)
- `voice/pipeline.py` (two new scheduled purge jobs; `_handle_internet_agent_turn()`'s new `enabled` gate)

## Expected Classes

None new.

## Expected Functions

- `KnowledgeGraphStore.purge_older_than(cutoff: datetime) -> int`
- `UsageStore.purge_older_than(cutoff: datetime) -> int`

Both return the count purged, matching `ConversationSessionStore.purge_older_than()`'s own existing return-shape precedent.

## Data Flow

Two new periodic flows, each mirroring the already-established purge pattern exactly: `TaskScheduler` tick → `purge_older_than(now - retention_window)` → rows deleted, count logged. `InternetConfig.enabled` gate: `_handle_internet_agent_turn()` checks the flag before `ResearchEngine.research()` is ever reached — no other change to the existing internet-agent flow.

## Implementation Tasks

1. `KnowledgeGraphStore.purge_older_than()`, staleness-based on `last_referenced_at`, degrading to `0` (never raising) on a SQLite failure, matching this store's own existing Sprint 6.14 degrade-on-read-failure precedent.
2. `UsageStore.purge_older_than()`, age-based on each sample's own timestamp, same degrade discipline.
3. `KnowledgeGraphConfig.retention_days`/`AnalyticsConfig.sample_retention_days` — new config fields, validated positive, generous defaults disclosed and justified in each field's own docstring.
4. Register both as new `resource_sensitive=True` `TaskScheduler` jobs in `voice/pipeline.py`'s `start()`/`stop()`.
5. `InternetConfig.enabled` — new field; `_handle_internet_agent_turn()` gate with an honest spoken degrade when `False`.
6. A dedicated egress-boundary regression test formalizing this sprint's own "good news" finding: a fake `SearchProvider`/`Summarizer` pair asserts the exact request payload sent contains only the current turn's own query text, never any `MemoryRecord`/`ConversationTurn`/`Entity` content — turning today's manual research confirmation into a permanent, enforced regression guard.
7. `backlog/technical_debt.md` — new item for the data-export/deletion gap, per Objectives.

## Architecture Notes

Both new purge methods and their own scheduled jobs are additive, optional-by-default-enabled infrastructure — no existing `KnowledgeGraphStore`/`UsageStore` caller's behavior changes. `InternetConfig.enabled` defaults `True` specifically so this sprint introduces a real, working opt-out without silently changing default behavior for every existing installation, matching this project's own "additive, backward-compatible by default" discipline used for every prior optional-collaborator/config addition.

## Integration Considerations

- Sprint 6.22 (Full Documentation Pass) is where the still-open "what do you know about me" gap gets its own permanent `backlog/technical_debt.md` cross-reference reviewed alongside every other open item, not re-litigated.
- Sprint 6.23 (Full Test Suite Pass) re-confirms this sprint's own new egress-boundary regression test as part of its own closing adversarial re-read.

## Potential Risks

- **A retention window set too short for `KnowledgeGraphStore` would silently discard genuinely durable facts** (a `PROJECT`/`PERSON` entity, unlike a chat turn, has no natural "this is now stale" signal beyond staleness itself) — the staleness-based (not creation-age-based) design and a deliberately generous default are the direct mitigation, disclosed explicitly rather than guessed at a tighter value.
- **The egress-boundary regression test (Implementation Task 6) could give false confidence if it only covers the CURRENT three search providers** — each provider's own request-building code is checked individually, not inferred from one provider's own correctness.

## Acceptance Criteria

- `KnowledgeGraphStore.purge_older_than()`/`UsageStore.purge_older_than()` both real, tested, and wired to genuine recurring `TaskScheduler` jobs — confirmed via a real SQLite-backed test proving old rows are actually removed and recent ones retained.
- `InternetConfig.enabled=False` reliably prevents any outbound network call, verified directly (not just that the reply changes).
- The egress-boundary regression test passes, formalizing the "only current-turn query text ever leaves the machine" finding as an enforced guarantee.
- `backlog/technical_debt.md` item 31 marked resolved; a new item logs the data-export/deletion gap.
- Full test suite (unit + integration + system, opt-in real-model marker excluded) passes with zero regressions.
- `ruff check .` clean.

## Testing Checklist

- [x] `KnowledgeGraphStore.purge_older_than()` — real SQLite round-trip.
- [x] `UsageStore.purge_older_than()` — real SQLite round-trip.
- [x] Both jobs genuinely recur via `TaskScheduler` (real, not mocked) — confirmed at the unit level (job registration, interval, resource_sensitive) and by real end-to-end construction in `tests/integration/conftest.py`/`tests/system/conftest.py`.
- [x] `InternetConfig.enabled=False` blocks the real outbound call path.
- [x] Egress-boundary regression test — real `SearchProvider`/`Summarizer` pair, proving `DecisionTrace`'s own carried memory/entity content never reaches the search boundary; each of the three real providers' own individual request-shape correctness was already independently covered pre-sprint (`test_search_sends_the_correct_request_shape` in each provider's own test file).
- [x] Full project suite re-run.

## Documentation Checklist

- [x] `docs/STATUS.md` — narrative describing both new purge mechanisms, the `internet.enabled` flag, and the egress-boundary finding.
- [x] `docs/sprint_book/INDEX.md` — 6.21 row → `Complete` (once implemented).
- [x] `docs/backlog/technical_debt.md` — item 31's own `internet.enabled` recommendation marked resolved (its separate real-API-verification gap remains explicitly open); new item 59 logs the data-export/deletion gap.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../../CODING_STANDARDS.md).

## Estimated Complexity

Medium.

## Estimated Development Time

2–2.5 days.

## Risks

See Potential Risks above.

## Next Sprint

6.22 — Full Documentation Pass.

## Future Considerations

- A real "what do you know about me" / data-export / data-deletion voice or UI surface — genuinely new conversational/UI capability this sprint deliberately doesn't build, per its own audit-and-harden scope; a strong candidate for a small, dedicated future sprint once prioritized.

## Sprint Completion Report (2026-08-16)

Implemented as specified, continued from a prior session's own "continue with sprint 6.21." No new `AskUserQuestion` gate was needed — every Objective was a direct, literal instruction.

**Objectives 1/2/3 (Implementation Tasks 1-4) — implemented exactly as specified.** `knowledge/knowledge_graph_store.py`'s `KnowledgeGraphStore.purge_older_than(days: int | None = None) -> int` and `analytics/usage_store.py`'s `UsageStore.purge_older_than(days: int | None = None) -> int` both mirror `ConversationSessionStore.purge_older_than()`'s exact established shape (a days-based default from the store's own config, cutoff computed internally, degrade-to-0-on-SQLite-failure) — a deliberate, disclosed correction from this sprint's own literal Expected Functions text (`purge_older_than(cutoff: datetime)`), chosen because a real `TaskScheduler.add_job()` requires a genuinely zero-arg callable (`Callable[[], None]`), the same constraint `conversation_store_purge`/`action_audit_log_purge` already satisfy via the identical days-default pattern. `KnowledgeGraphStore`'s own version is staleness-based (`last_referenced_at`, not `created_at`) exactly as the Objectives require; new `KnowledgeGraphConfig.retention_days` (365) / `AnalyticsConfig.sample_retention_days` (90), both validated positive. Both registered as new `resource_sensitive=True` `TaskScheduler` jobs in `voice/pipeline.py`'s `start()`/`stop()`, each None-guarded (Level 6 Part A / Level 5 Part B collaborators respectively) — `CommunicationPipeline` gained three new constructor parameters (`knowledge_graph_store`, `usage_store`, `internet_config`), threaded through `main.py`'s `_construct_pipeline()` and both `tests/integration/conftest.py`'s/`tests/system/conftest.py`'s own real-construction harnesses (not mocked at that layer — both already held local `knowledge_graph_store`/`usage_store`/`internet_config` variables for other collaborators' own construction, so no new fixture setup was needed, only new keyword arguments at the existing `CommunicationPipeline(...)` call sites).

**Objective 4 (Implementation Task 5) — implemented.** New `InternetConfig.enabled: bool = True`; `_handle_internet_agent_turn()` checks it first, before `ResearchEngine.research()` is ever reached, degrading to "Internet research is currently turned off." — closing `backlog/technical_debt.md` item 31's own long-open recommendation. A deliberate, disclosed partial resolution, not a blanket "item 31 closed" claim: that item also tracks a separate, still-open real-API-verification gap (the opt-in `real_search_api`-marked test has never run against a live key), explicitly left open in the same backlog entry.

**Implementation Task 6 (egress-boundary regression test) — implemented as a pipeline-level test, not a per-provider one.** Each of the three real `SearchProvider` implementations already had its own pre-existing `test_search_sends_the_correct_request_shape`-style test (proving *that provider* forwards whatever query string it's given correctly and nothing else) — re-confirmed still passing, satisfying this sprint's own Potential Risk #2 ("each provider's own request-building code is checked individually"). The genuinely new, more valuable guard this sprint adds sits one layer up: `test_internet_agent_egress_boundary_never_leaks_memory_or_entity_content` (`tests/unit/voice/test_pipeline.py`) proves the *pipeline itself* never lets memory/entity content reach the query in the first place — `DecisionTrace` (the object `_handle_internet_agent_turn()` receives) carries real `retrieved_memories`/`mentioned_entities` content on the SAME object the method reads `context_analysis.primary_topic`/`intent.raw_transcript` from; a real, non-mocked `_CapturingSearchProvider`/`_CapturingSummarizer` pair (wired through a real `ResearchEngine`, not a `MagicMock`) proves only the topic string ever arrives, with explicit assertions that two distinctive "secret" marker strings (standing in for memory/entity content) never appear in what was captured.

**A real, disclosed judgment call on backlog item 31.** Rather than mechanically flipping the whole row to "(resolved)" per this sprint's own literal Acceptance Criteria wording, only the specific `internet.enabled` recommendation within that item's own text is marked resolved — the item's own separate, still-genuinely-open real-API-verification gap is called out explicitly as NOT resolved by this sprint, matching this project's own established "no dishonest resolved-marking" discipline (e.g. item 57's own "encrypt secrets only" scoping at Sprint 6.20).

**Full regression suite.** `tests/unit/`: 2298 passed, 1 skipped (17 new tests across `test_knowledge_graph_store.py`, `test_usage_store.py`, `test_schema.py`, `test_pipeline.py` — zero regressions from the 2281+1 baseline). `tests/integration/`: 75 passed on a clean re-run; one earlier combined run saw `test_reminder_becoming_due_during_session_end_never_corrupts_state` fail once, individually and full-file re-confirmed passing (a resource-contention flake this specific test file's own docstring already discloses as an accepted characteristic of its 0.3s-interval harness, not a regression — this sprint's own two new jobs add a small amount of scheduling contention to that already-contention-tolerant harness, not a new failure mode). `tests/system/`: 33 passed, 4 skipped, 1 failed on the combined run (`test_full_level3_acceptance_scripted_conversation`) — the same test already known flaky under full-suite host contention (confirmed at Sprint 6.20), re-confirmed passing standalone here too. Zero real regressions. `ruff check .` clean repo-wide. No git commit made — sits uncommitted alongside all of 6.1-6.20's own backlog.
