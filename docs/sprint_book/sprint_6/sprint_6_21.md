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

- [ ] `KnowledgeGraphStore.purge_older_than()` — real SQLite round-trip.
- [ ] `UsageStore.purge_older_than()` — real SQLite round-trip.
- [ ] Both jobs genuinely recur via `TaskScheduler` (real, not mocked).
- [ ] `InternetConfig.enabled=False` blocks the real outbound call path.
- [ ] Egress-boundary regression test, all three search providers.
- [ ] Full project suite re-run.

## Documentation Checklist

- [ ] `docs/STATUS.md` — narrative describing both new purge mechanisms, the `internet.enabled` flag, and the egress-boundary finding.
- [ ] `docs/sprint_book/INDEX.md` — 6.21 row → `Complete` (once implemented).
- [ ] `docs/backlog/technical_debt.md` — item 31 resolved; new data-export/deletion item logged.

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
