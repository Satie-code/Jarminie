# Sprint 5.20 — Analytics Dashboard Data

## Sprint ID

5.20

## Sprint Name

Analytics Dashboard Data

## Purpose

Turn Sprint 5.17's raw `AppFocusSample`/`UsageSession` data into aggregate, meaningful statistics — per `02_System_Architecture.md`'s Analytics Engine ("Tracks: Productivity, Habit consistency, Project progress, Focus sessions, Screen time, Application usage. Statistics are used only for improving user experience.") and `04_Master_Implementation_Plan.md`'s Phase 5.3 Acceptance Criteria ("Reliable analytics. Meaningful insights."). Deliberately data-only, per this sprint's own name — no dashboard widget/UI is built here.

## Engineering Rationale

Corresponds to the roadmap-granularity `Analytics Dashboard Data` entry (originally numbered `5.21`, Phase 5.3), renumbered to `5.20` per this Sprint Book's own real build order — its one real dependency (Sprint 5.17) is now satisfied.

**A real, disclosed scoping narrowing on "Project progress"**: Part 2 names it as one of six things the Analytics Engine tracks, but nothing anywhere in this codebase — across all of Levels 1–5 Part A and Sprint 5.17 — has ever built a concept of a user-declared "project" (as distinct from a plain application or file). Fabricating one now, with no real data behind it, would be exactly the kind of ungrounded metric this project's own Explainability Rule and the Internet Agent's own "never a fabricated verified badge" precedent (`internet/source_validator.py`, Sprint 4.17) both argue against. This sprint instead reuses `AnalyticsConfig.category_map` (Sprint 5.17) — the same config-driven `process_name -> category` map — treating a "project" as a best-effort proxy: time spent under any category the user has themselves labeled (e.g. mapping several project-specific IDE/terminal window titles to a shared category string), openly narrower than genuine multi-project tracking, and documented as such rather than silently overstated (the identical honesty precedent `sprint_5_7.md`'s own `_derive_ring_state()` limitation, and `sprint_4_17.md`'s grounding-limitation disclosure, both already established for this project).

**No dashboard UI is built in this sprint, deliberately** — this Sprint Book names no UI sprint for Analytics anywhere in its own roadmap-granularity table (unlike Level 5 Part A's dedicated Presentation Layer sprints), and `ui/status_panel.py`/`ui/main_window.py` are not in this sprint's own Files to Modify. A real display surface is a genuine, disclosed Future Consideration, matching Level 6's own eventual scope rather than being invented here without a named requirement.

## Objectives

- `DailySummary`, `HabitConsistency`, and `ProjectProgressSummary` — the three aggregate shapes this sprint produces.
- `AnalyticsDashboardService`: composes `UsageStore` (5.17) queries into the above, on demand (not itself a background job — see Architecture Notes).

## Dependencies

5.17 (Usage & Habit Tracking — `UsageStore`, `UsageSession`, `AnalyticsConfig.category_map`, the sole real data source this sprint reads).

## Files to Create

- `analytics/dashboard_data.py` — `DailySummary`, `HabitConsistency`, `ProjectProgressSummary` (dataclasses), `AnalyticsDashboardService`.
- `tests/unit/analytics/test_dashboard_data.py`

## Files to Modify

- `config/schema.py` — `AnalyticsConfig` gains `habit_category_names: tuple[str, ...] = ()` (which `category_map` values count as a "habit" for `HabitConsistency` purposes — e.g. `("coding",)` — empty by default, no basis for a built-in guess), `project_category_names: tuple[str, ...] = ()` (the same idea for the "Project progress" proxy named above — deliberately a *separate* field from `habit_category_names`, since a category can be a habit without being a project-scoped one, or vice versa), `habit_consistency_window_days: int = 7` (Part 2's own implicit weekly framing — "consistency" needs a window).
- `config/defaults.yaml` — matching new `AnalyticsConfig` fields.

## Expected Classes

- `DailySummary` (dataclass) — `date: date`, `total_active_seconds: float`, `top_applications: list[tuple[str, float]]` (process name, seconds — sorted descending, capped at `AnalyticsConfig.top_applications_limit`), `focus_session_count: int`, `longest_focus_session_seconds: float`.
- `HabitConsistency` (dataclass) — `category: str`, `window_days: int`, `days_with_activity: int`, `consistency_ratio: float` (`days_with_activity / window_days`, always 0.0–1.0).
- `ProjectProgressSummary` (dataclass) — `category: str`, `window_days: int`, `total_seconds: float`, `session_count: int` — deliberately no "progress" judgment of any kind (no percentage-complete, no trend arrow) — see Engineering Rationale's own narrowing.
- `AnalyticsDashboardService` — constructor DI: `(usage_store: UsageStore, analytics_config: AnalyticsConfig)`. Stateless beyond its own constructor DI — every method computes fresh from `usage_store` at call time, never caches (the same "no staleness to reason about" simplicity `decision/context_analyzer.py`'s own stateless design already established).

## Expected Interfaces

None new.

## Expected Functions

- `AnalyticsDashboardService.daily_summary(target_date: date) -> DailySummary` — queries `usage_store.list_sessions_since()` for the given calendar day (local time), aggregates.
- `AnalyticsDashboardService.habit_consistency(category: str, window_days: int | None = None) -> HabitConsistency` — `window_days` defaults to `AnalyticsConfig.habit_consistency_window_days`; counts distinct calendar days within the window that have at least one `UsageSession` whose `.category == category`.
- `AnalyticsDashboardService.project_progress(category: str, window_days: int | None = None) -> ProjectProgressSummary` — same window default, sums `.ended_at - .started_at` across matching sessions.
- `AnalyticsDashboardService.all_habit_consistency() -> list[HabitConsistency]` — convenience wrapper over `analytics_config.habit_category_names`.

## Data Flow

```
caller (Sprint 5.24's live turn handler, or a future dashboard UI)
      ↓
AnalyticsDashboardService.daily_summary(date.today())
      ↓
UsageStore.list_sessions_since(start_of_day)
      ↓
aggregate (top apps, focus session count/length, total active time)
      ↓
DailySummary
```

## Implementation Tasks

1. `config/schema.py`/`config/defaults.yaml` — new `AnalyticsConfig` fields.
2. `analytics/dashboard_data.py` — the three dataclasses, `AnalyticsDashboardService` and its four methods.
3. Unit tests: `daily_summary()` aggregation correctness against a fixed set of fixture sessions (top-N ordering and cap, focus-session count/longest, total active seconds); `habit_consistency()`'s ratio against a fixture spanning both matching and non-matching days, including a day with zero sessions at all; `project_progress()`'s sum against fixture sessions; an empty `UsageStore` (no sessions at all) producing a valid, zeroed `DailySummary`/`HabitConsistency`/`ProjectProgressSummary` rather than raising.

## Architecture Notes

`AnalyticsDashboardService` is deliberately *not* a `ManagedModule` and registers no `TaskScheduler` job of its own — every method is a plain, synchronous, on-demand query over already-persisted data (mirroring `memory/retrieval_engine.py`'s `MemoryRetrievalEngine`'s own "composes stores, holds no state of its own" precedent from Sprint 3.9). This keeps this sprint's own real cost proportional to how often a caller actually asks, rather than continuously recomputing statistics nobody has requested yet — a deliberate contrast to Sprint 5.17's/5.18's own always-ticking trackers, both of which have a real reason to run continuously (raw sampling; time-based trigger detection) that a pure aggregation query does not share.

The "Project progress" proxy's own honesty boundary is structural: `ProjectProgressSummary` has no field that could be mistaken for a genuine completion percentage or milestone list — only time and session count, the two things `UsageStore`'s own data can actually support without fabrication.

## Integration Considerations

- No live caller exists yet — Sprint 5.24's job, whether that is a live conversational query ("how's my day looking," routed through `EngineSelection.WELLNESS` or a new narrow analytics-query path) or simply logged/available for a future dashboard UI.
- Sprint 5.21 (Pattern Recognition) is this sprint's own real, immediate consumer within this Sprint Book — `PatternRecognizer.detect_work_habits()` calls `habit_consistency()` rather than reimplementing the same aggregation, per the Dev Guide's own "extend or improve existing functionality instead of recreating it" Step 1 rule.

## Potential Risks

- **`daily_summary()`'s "calendar day" is computed in local system time**, with no timezone-configuration surface anywhere in this codebase — consistent with every other local-time assumption already made throughout (e.g. `WellnessConfig.late_night_start_hour`), not a new gap this sprint introduces, but worth naming since aggregation is exactly where a silent off-by-one-day bug would first surface.
- **The "Project progress" proxy is only as good as the user's own `category_map`/`project_category_names` configuration** — with both empty (the honest default), `project_progress()` for any category simply returns a zeroed summary rather than an error, correctly reflecting "nothing configured" rather than pretending to have data.
- **No caching means a caller polling `daily_summary()` frequently re-scans `UsageStore` every time** — acceptable at this project's own single-user, local-SQLite scale (the same reasoning that lets `MemoryRetrievalEngine` and others skip caching too), flagged only so a future high-frequency caller does not assume otherwise.

## Acceptance Criteria

- `daily_summary()` correctly aggregates total active time, top-N applications (ordered, capped), and focus-session count/longest-duration against a known fixture.
- `habit_consistency()`'s ratio is exact against a fixture with a known number of matching days within the window.
- `project_progress()`'s totals are exact against a fixture.
- Every method degrades to a valid, zeroed result (never an exception) against an entirely empty `UsageStore`.
- No field anywhere in `ProjectProgressSummary` implies a completion percentage or milestone judgment not actually computed.

## Testing Checklist

- [ ] Unit: `daily_summary()` aggregation (top-N ordering/cap, focus sessions, total time).
- [ ] Unit: `habit_consistency()` ratio, including a zero-activity day and a zero-window edge case.
- [ ] Unit: `project_progress()` totals.
- [ ] Unit: `all_habit_consistency()` iterates `habit_category_names` correctly.
- [ ] Unit: every method against an empty `UsageStore`.

## Documentation Checklist

- [ ] `analytics/dashboard_data.py` docstring: the "Project progress" narrowing, stated explicitly (per Engineering Rationale above).
- [ ] `docs/STATUS.md` — Phase 5.3 (Analytics) narrative updated; row stays `Developing`.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../../CODING_STANDARDS.md).

## Estimated Complexity

Low–Medium.

## Estimated Development Time

1–1.5 days.

## Risks

See Potential Risks above.

## Next Sprint

5.21 — Pattern Recognition.

## Future Considerations

- A real dashboard UI surface (Jarvis's own workspace panels, Sprint 5.12's `_SystemStatusPanel` precedent, or a dedicated new panel) — genuinely out of this Sprint Book's own named scope.
- True multi-project tracking (explicit user-declared projects, not a category proxy) — the real narrowing named above.
- Trend/comparison statistics (this week vs. last week) — no basis in Part 2's own text, not built speculatively.
