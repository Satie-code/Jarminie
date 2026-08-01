# Sprint 4.16 — Search & Research

## Sprint ID

4.16

## Sprint Name

Search & Research

## Purpose

Give the Internet Agent its research/search half, per `02_System_Architecture.md`'s Internet Agent section (*"Research. Search. Summarization. Source comparison. Source validation... should prioritize trustworthy sources... clearly distinguish between verified facts and uncertain information"*) and `04_Master_Implementation_Plan.md`'s Phase 4.4 (*"Research. Search. Summarization. Source comparison. Validation."*). This sprint covers Search only — Summarization & Source Validation is Sprint 4.17, the same storage/execution-shaped split this Sprint Book has already used for Calendar/Reminder (4.14/4.15) and Level 4 Part A used for Workflow (4.9/4.10).

## Engineering Rationale

Corresponds to `docs/sprint_book/INDEX.md`'s roadmap-granularity `4.16 Search & Research` entry, expanded to full detail alongside the rest of this Sprint Book (2026-07-31).

**A real, significant architectural threshold, flagged explicitly rather than silently crossed**: every prior sprint in this project reaches only local resources — a local LLM (Ollama), local models (Whisper, Coqui, openWakeWord), and local storage (SQLite, ChromaDB). **This is the first sprint in JARMINEI's history whose whole purpose is making outbound requests to the public internet on the user's behalf.** That is a real privacy- and reliability-relevant boundary crossing (what the user asked JARMINEI to search for leaves the machine; the search provider's own availability/rate limits/terms of service now affect JARMINEI's own behavior), worth naming plainly in this Sprint Book rather than treating it as "just another executor," the same seriousness this project already gave Sprint 4.5 (Command Execution Engine, "the highest-risk [executor] in Part A") and Sprint 4.7's `approved_emergency_procedures` gate.

**Part 3's technology stack (`03_Engineering_Standards.md`) names no search provider or HTTP library at all** — unlike every other external dependency in this project (Ollama, Whisper, openWakeWord, Coqui, ChromaDB, APScheduler, pywin32 are all explicitly named), the Internet Agent's own backing service is entirely unspecified. This is a genuine, consequential decision with no single obviously-correct default (unlike, say, `coqui-tts` vs. the archived `TTS` package, where only one option was actually viable) — real options trade off cost, reliability, ToS compliance, and setup friction against each other:

- **A keyed API** (e.g. Bing Web Search API, Google Programmable Search Engine, Brave Search API) — reliable, ToS-compliant, structured results with real snippets/metadata that make Sprint 4.17's citation work easy and honest, but requires the user to obtain and configure an API key (and, for most of these, accept a paid tier or a capped free quota) before this sprint's own capability does anything real.
- **An unauthenticated HTML-scraping approach** (e.g. DuckDuckGo's own HTML/lite search endpoint) — no signup, no cost, works immediately, but is fragile (an unversioned HTML contract that can silently break), sits in a real automated-scraping ToS gray area this project has not evaluated, and produces messier, less structured source metadata that makes Sprint 4.17's "clear citations" requirement harder to satisfy honestly.

**Per this project's own standing "ask before any architecturally significant, externally-visible decision" rule** (the same rule that gated Sprint 2.4's `espeak-ng` system install and Sprint 4.7's `approved_emergency_procedures` whitelist), **this sprint's own concrete search-provider choice is deliberately left as an explicit, named stop-and-ask gate for whoever implements it, not decided here.** `SearchClient` is specified below as a `Protocol` (the same model-independence discipline `03_Engineering_Standards.md` mandates for the AI Runtime and Speech-to-Text — *"the architecture must remain model-independent"* — applied here to search providers for an identical reason) so that decision doesn't block writing the rest of this sprint's shape; only the one concrete adapter class waits on it. A keyed API is the **recommended** default (reliability and ToS-cleanliness matter more here than for, say, a wake-word stand-in phrase) but the actual choice — including whether the user already holds a preferred provider/key — is the user's to make, consistent with `backlog/technical_debt.md`'s own treatment of every prior externally-visible dependency choice in this project.

## Objectives

- `SearchResult` (one search hit: title, URL, snippet, retrieved-at timestamp).
- `SearchClient` (Protocol) — the model-independent search-provider contract, mirroring `decision/llm_client.py`'s `LanguageModelClient` Protocol precedent exactly.
- One concrete `SearchClient` implementation, backed by whichever provider the stop-and-ask gate above resolves to.
- `ResearchEngine` — orchestrates a query into a bounded, ranked set of `SearchResult`s; the object Sprint 4.17's summarization consumes.
- `InternetConfig` (new `config/schema.py` section).

## Dependencies

3.11 (Authority Evaluation & Engine Selection, per `docs/sprint_book/INDEX.md`'s roadmap dependency — `EngineSelection.INTERNET_AGENT` already exists as a reserved value since Sprint 3.11, this sprint is what eventually backs it, wired for real at Sprint 4.18).

## Files to Create

- `internet/search_client.py` — `SearchResult` (dataclass), `SearchClient` (Protocol), the one concrete provider adapter (name depends on the provider decision above).
- `internet/research_engine.py` — `ResearchEngine`.
- `tests/unit/internet/test_search_client.py`
- `tests/unit/internet/test_research_engine.py`

## Files to Modify

- `config/schema.py` — new `InternetConfig` dataclass: `max_results_per_query: int = 5` (a defensive bound, same category as `WorkflowConfig.max_steps_per_workflow`), `request_timeout_seconds: float = 10.0`, plus whichever provider-specific field (e.g. `search_api_key: str | None`) the stop-and-ask gate's outcome requires.
- `config/defaults.yaml` — matching `internet:` section.
- `requirements.txt` — the HTTP client library this sprint needs (`requests` or `httpx` — neither currently a direct dependency of this project; `ollama`'s own client library may already pull one in transitively, worth checking before adding a duplicate) and, if the keyed-API path is chosen, no additional package (a plain authenticated HTTP call needs nothing beyond the HTTP client itself).

## Expected Classes

- `SearchResult` (dataclass) — `title: str`, `url: str`, `snippet: str`, `retrieved_at: datetime`.
- `SearchClient` (Protocol) — `search(self, query: str, max_results: int) -> list[SearchResult]`.
- The concrete adapter (e.g. `BingSearchClient`/`DuckDuckGoSearchClient`, name TBD per the provider decision) implementing `SearchClient`.
- `ResearchEngine` — constructor DI: `(search_client: SearchClient, internet_config: InternetConfig)`. Not a `ManagedModule` — no thread/connection/hardware of its own to start/stop, the same "stateless-per-call aggregator" reasoning `sprint_2_8.md` gave for `ContextManager` not being a `ManagedModule` either.

## Expected Interfaces

- `SearchClient` (Protocol), per Expected Classes above.

## Expected Functions

- `ResearchEngine.research(query: str) -> list[SearchResult]` — calls `search_client.search()`, bounded by `internet_config.max_results_per_query`, degrading to an empty list (never raising) on any `SearchClient` failure — the same fail-gracefully-by-default posture `decision/intent_detector.py`'s Ollama-unreachable handling already established for an external-service dependency, applied here to the network as a whole (unreachable, timed out, rate-limited, malformed response) rather than deferred entirely to Sprint 4.19's own hardening pass, since a query that silently returns nothing is a far safer default failure mode for a network-facing feature than one that raises into a live conversation turn.

## Data Flow

```
"What's the latest on X?" (a query, from a live conversation turn or a future
non-voice caller — Sprint 4.18 decides which for real)
      ↓
ResearchEngine.research(query)
      ↓
SearchClient.search(query, max_results) → [SearchResult, SearchResult, ...]
      ↓
Sprint 4.17 (Summarization & Source Validation)
```

## Implementation Tasks

1. **Stop-and-ask gate**: confirm the search provider choice with the user before writing the concrete `SearchClient` adapter (per Engineering Rationale above) — the `SearchResult`/`SearchClient` Protocol/`ResearchEngine` shapes can be written and unit-tested against a fake `SearchClient` regardless of the outcome, so this gate does not need to block the rest of the sprint's own work.
2. `config/schema.py`/`config/defaults.yaml` — `InternetConfig`.
3. `internet/search_client.py` — `SearchResult`, `SearchClient`, the concrete adapter.
4. `internet/research_engine.py` — `ResearchEngine`.
5. Unit tests: `ResearchEngine` against a fake `SearchClient` (bounding, degradation-on-failure); the concrete adapter against a real network call, isolated and clearly marked (matching `tests/system/test_level3_real_model_verification.py`'s own established "opt-in real-network/real-model test, skipped by default" precedent — never a required part of the fast suite, since a real network call is exactly the kind of non-deterministic, environment-dependent test this project has consistently kept out of its default `pytest -q` run).

## Architecture Notes

`SearchClient` as a `Protocol` (not an ABC) matches `decision/llm_client.py`'s `LanguageModelClient` precedent exactly, for the identical reason Part 3 states for the AI Runtime: *"the architecture must remain model-independent so that additional models can be integrated later without significant refactoring."* Applied here: swapping search providers later (a different API, or adding a second one for redundancy) means writing one new adapter class, not touching `ResearchEngine` at all.

`internet/` has no dependency on `voice/`, `decision/`, or any other subsystem beyond its own `config/` section — the same dependency-direction leaf discipline `scheduler/` (4.14/4.15) already follows. Whatever calls `ResearchEngine.research()` from a live conversation turn is Sprint 4.18's own concern, not this sprint's.

## Integration Considerations

- No live caller exists yet — `ResearchEngine.research()` is real, callable, and tested, but nothing wires a conversation turn (`EngineSelection.INTERNET_AGENT`) or any other caller to it. Sprint 4.18's job, mirroring `sprint_4_9.md`'s/`sprint_4_14.md`'s own identical "storage/mechanism sprint defers live wiring" precedent.
- Sprint 4.17 (Summarization & Source Validation) is the sole consumer of `ResearchEngine.research()`'s output within this Sprint Book's own scope.
- This sprint's real, significant privacy-boundary crossing (Engineering Rationale above) is worth a `docs/backlog/technical_debt.md` entry of its own once the provider decision is actually made — recording which provider, what data leaves the machine (the query text only, or more), and under what configuration (e.g. a config flag to disable Internet Agent entirely, worth considering at Sprint 4.18 or Sprint 4.19 if not built here) — named now so it isn't silently forgotten once implementation starts.

## Potential Risks

- **The provider decision itself is the largest risk this sprint carries** — an unresolved or poorly-chosen provider affects every downstream sprint (4.17, 4.18, 4.20) that assumes real search results exist to summarize/cite/verify. Resolving it first, explicitly, before any adapter code is written, is why Implementation Task 1 is a stop-and-ask gate rather than an assumption.
- **No caching** — every `research()` call is a real network round trip; a user repeating a similar query in quick succession (or Sprint 4.17 re-querying for validation) re-fetches from scratch. Acceptable for this sprint's own scope (Part 2 names no caching requirement, and `03_Engineering_Standards.md`'s own Cache Layer — JSON, "fast local caching... temporary configuration... session state" — is not scoped to research results), flagged as a Future Consideration, not built speculatively.
- **Rate limiting / quota exhaustion** (real for almost every provider option) — this sprint's own `research()` degrades to an empty result list on any `SearchClient` failure per Expected Functions above, so a rate-limit response fails safely, but the *user-facing* experience of "why did JARMINEI say it found nothing" during a real quota exhaustion is a Sprint 4.19 (Error Handling & Recovery Hardening) named scenario, not fully solved here.
- **No content fetching in this sprint** — `SearchResult.snippet` is whatever the search provider itself returns (typically a short excerpt), not the full page content. Sprint 4.17 decides whether summarization works from snippets alone or needs a real page-fetch step; not assumed either way here.

## Acceptance Criteria

- `ResearchEngine.research(query)` returns at most `max_results_per_query` `SearchResult`s for a real, successful query against the chosen provider.
- A `SearchClient` failure (network unreachable, timeout, non-2xx response, malformed payload) degrades `research()` to an empty list, never an unhandled exception reaching the caller.
- The concrete `SearchClient` adapter's own unit test, run opt-in against the real provider, returns plausible, real results for a known, stable query.
- `InternetConfig`'s bounds (`max_results_per_query`, `request_timeout_seconds`) are genuinely enforced, not merely declared.

## Testing Checklist

- [ ] Unit: `ResearchEngine.research()` against a fake `SearchClient` — bounding, ordering, pass-through of real results.
- [ ] Unit: `ResearchEngine.research()` degrades to `[]` on a fake `SearchClient` raising each of: connection error, timeout, malformed response.
- [ ] Opt-in/real (skipped by default, matching `test_level3_real_model_verification.py`'s precedent): the concrete adapter against the real provider for a known query.
- [ ] Unit: `request_timeout_seconds`/`max_results_per_query` are genuinely passed through and enforced, not just stored.

## Documentation Checklist

- [ ] `internet/search_client.py` docstring: the provider decision actually made, and why (mirroring how `voice/text_to_speech.py`'s docstring documents the `coqui-tts` vs. `TTS` package decision).
- [ ] `backlog/technical_debt.md` — new entry per Integration Considerations above, once the provider decision is made.
- [ ] `docs/STATUS.md` — Phase 4.4 (Internet Agent) row moves to `Designing`.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md).

## Estimated Complexity

Medium.

## Estimated Development Time

1.5–2 days (excluding time spent on the provider stop-and-ask gate itself, which could add a real, unbounded delay if the user needs to obtain/configure an API key).

## Risks

See Potential Risks above.

## Next Sprint

4.17 — Summarization & Source Validation.

## Future Considerations

- Result/query caching — flagged above, not built now.
- A second, redundant search provider for resilience — no basis in Part 2's own text; would only be worth building if the first provider proves unreliable in real use.
- Full page-content fetching (beyond the provider's own snippet) — Sprint 4.17's own decision to make, not pre-built here.

## Sprint Completion Report (2026-07-31)

**Stop-and-ask gate resolved first, per this sprint's own Implementation Task 1**: asked the user via `AskUserQuestion` (two questions — provider, then key-delivery mechanism). User chose a keyed API generally, then **Brave Search API** specifically (over Google Programmable Search Engine, citing its simpler single-header auth), with the key delivered via an **environment variable** (`JARMINEI_INTERNET_SEARCH_API_KEY`, matching this project's existing `JARMINEI_<SECTION>_<FIELD>` convention) rather than `config/local.yaml`. Implementation then proceeded directly ("continue to the implementation of sprint 4.16"), no further stop-and-ask needed.

Delivered `internet/search_client.py` (`SearchResult`, `SearchClient` Protocol, `BraveSearchClient`, `SearchError`), `internet/research_engine.py` (`ResearchEngine`), `InternetConfig` in `config/schema.py`/`config/defaults.yaml`/`config/loader.py`. `requests` (already an indirect dependency) added explicitly to `requirements.txt` as this sprint's first direct caller. 16 new tests (12 in `test_search_client.py`, 4 in `test_research_engine.py`) — `requests.get` mocked at the boundary in every fast test, matching `test_text_to_speech.py`'s own established "mock the external library call" precedent; a 17th test (marked `@pytest.mark.real_search_api`, a new marker registered in `pyproject.toml`) exercises the real Brave API and skips cleanly since no real API key was available in this development session. `ruff check .` clean.

**No API key was available this session, so the real provider was never actually called** — `BraveSearchClient`'s response parsing (`web.results[].title`/`url`/`description`) was implemented from Brave's own published API documentation, not verified against a live response. Logged honestly as `backlog/technical_debt.md` item 31 rather than silently presented as fully verified — the opt-in `real_search_api`-marked test exists specifically so this can be confirmed for real the moment a key is configured, without writing any new test at that point.

**`docs/backlog/technical_debt.md` item 31 also records this sprint's own real privacy-boundary crossing** (per its own Engineering Rationale) — exactly what data leaves the machine (only the raw query text, over HTTPS, plus the API key as a header; never conversation/memory content, since `ResearchEngine`/`BraveSearchClient` have no access to either) and that no user-facing opt-out flag exists yet for the Internet Agent as a whole, flagged as worth a deliberate decision at Sprint 4.18/4.19, not assumed either way.

Full-suite run: 974 total, 957 passing, 1 skipped (the real-API test, correctly), 16 failed — the same 15 already-tracked `test_text_to_speech.py` failures plus one new-looking failure, `tests/system/test_level3_acceptance.py::test_full_level3_acceptance_scripted_conversation`. Investigated before dismissing: confirmed passing standalone (4/4), and this sprint's own changes touch only `internet/`/`config/`/`pyproject.toml` — nothing `test_level3_acceptance.py` depends on. Notably, this is a **different** system test than the one that flaked during Sprint 4.15's own full-suite run (`test_level4_part_a_full_acceptance_scenario`) — a different acceptance test failing each time, always passing standalone, is itself further evidence this is genuine host-resource-contention noise under ~975 concurrently-run tests (the same well-established flake class this project has hit repeatedly across every prior level), not a deterministic regression tied to any one sprint's own changes.

`docs/STATUS.md` (Phase 4.4 → `Developing`) and `docs/sprint_book/INDEX.md` (4.16 row → `Complete`) both updated. `ResearchEngine.research()` has no live caller yet — Sprint 4.18's job, alongside `TaskScheduler`/`ReminderEngine` from Sprint 4.15. **Sprint 4.17 (Summarization & Source Validation) is next.**

## Post-Sprint Revision (2026-08-01) — Provider-Agnostic Refactor

**User request, after Sprint 4.17 had already closed Internet Agent's own component work**: *"Do not make Brave Search a required dependency. Refactor the Internet module to use a Search Provider interface so multiple search providers can be plugged in. Implement Brave as one provider, but design the architecture to support alternative providers (e.g., Tavily, SerpAPI, SearXNG, or future providers) through configuration. The Internet subsystem should remain provider-agnostic."* A direct architectural directive, not a stop-and-ask gate — implemented immediately, documented here as a dated addendum to this sprint's own file (the sprint that owns `internet/`'s search half) rather than silently rewritten into the Sprint Specification/Completion Report above, matching this project's own established "Post-Sprint Fix" convention for changes discovered/requested after a sprint has already closed.

**What was already provider-agnostic, confirmed before changing anything**: `ResearchEngine` (this sprint) always depended on the `SearchClient` Protocol, never on `BraveSearchClient` concretely — that half of the "provider-agnostic" goal was already true. **What genuinely wasn't**: there was only one concrete implementation, no config-driven way to select a different one, and `InternetConfig`'s own docstring flatly asserted "Backed by the Brave Search API" as if that were fixed rather than a swappable default.

**Restructured `internet/`'s search half into three files**, mirroring `device_control/action_engine.py`'s own established "shared contract in one file, each concrete implementation in its own sibling file" precedent (`application_manager.py`/`file_operations.py`/`window_manager.py`/`command_executor.py`), rather than a heavier registry-class pattern this project's own scale doesn't yet need:
- `internet/search_provider.py` — `SearchResult`, `SearchError`, and the **renamed** `SearchProvider` Protocol (was `SearchClient` in `search_client.py`, now deleted). The rename to "Provider" (departing from `LanguageModelClient`'s own "Client" naming convention) was the user's own explicit terminology, not an unreviewed drift — documented as a deliberate choice in the module's own docstring.
- `internet/brave_search_provider.py` — `BraveSearchProvider` (renamed from `BraveSearchClient`, moved out of the old `search_client.py`, zero behavior change to its own logic).
- `internet/search_provider_registry.py` (new) — `create_search_provider(internet_config) -> SearchProvider`, a plain function-based registry (a dict + one factory function, not a stateful class — deliberately simpler than `ActionRegistry`, since exactly one provider is ever active at a time, unlike `ActionRegistry`'s many-executors-by-type shape) and `UnknownSearchProviderError`, raised with every registered provider name listed, for a construction-time misconfiguration.

**`InternetConfig` gained `search_provider: str = "brave"`** (the selector `create_search_provider()` reads) **and `search_base_url: str | None = None`** (a second generic field, alongside the already-generic `search_api_key`, anticipating a self-hosted provider like SearXNG that needs a base URL and typically no key at all — added now, unused by `BraveSearchProvider`, specifically so a future provider needing it doesn't also require another `InternetConfig` schema change). `search_provider` is deliberately validated only as "non-blank" in `config/schema.py`, not cross-checked against the real registry — `config/` is a dependency-direction leaf (nothing in it imports `internet/` or any other subsystem package, the same discipline `SecurityConfig.risk_policies` already follows), so an unregistered provider name surfaces a loud `UnknownSearchProviderError` at construction time instead, never a silent config-load-time assumption.

**Migrated and renamed the existing test suite to match**: `test_search_client.py` → `test_brave_search_provider.py` (identical test logic, `BraveSearchClient` → `BraveSearchProvider`, `SearchClient` → `SearchProvider` in imports), plus two new files — `test_search_provider.py` (the shared `SearchResult` dataclass) and `test_search_provider_registry.py` (5 tests: default/explicit "brave" both resolve correctly, the constructed provider genuinely receives the real config — verified via its one observable side effect, the API key it actually sends, not by reaching into a private attribute — and an unknown provider name raises `UnknownSearchProviderError` naming every real registered option). `test_research_engine.py`'s own `FakeSearchClient` local double renamed `FakeSearchProvider`, `ResearchEngine`'s constructor param renamed `search_provider`. `internet/summarizer.py`/`source_validator.py` needed only an import-path fix (`internet.search_client` → `internet.search_provider`) — neither ever referenced `BraveSearchClient` directly, confirming Sprint 4.17's own dependency boundary was already clean.

**Deliberately NOT built**: real `SearchProvider` implementations for Tavily, SerpAPI, or SearXNG. The user's own request named these as examples of what the architecture should be able to *support through configuration*, not a checklist of integrations to ship today — building three more real HTTP integrations from documentation alone (the same "not verified against a live call" caveat already logged for Brave in `backlog/technical_debt.md` item 31, now tripled) without the user having chosen or keyed any of them would be real, unrequested, unverifiable scope creep. `internet/search_provider_registry.py`'s own docstring spells out exactly the two steps adding one takes, so this is a genuine "swap the adapter" architecture, not just a promise — confirmed structurally by the fact that adding a provider requires touching `_PROVIDERS` in exactly one file and nothing else.

`backlog/technical_debt.md` item 31 updated to reflect the rename and to note explicitly that Brave remains the only *implemented* provider even though it's no longer the only *possible* one — the underlying real-verification gap (no live Brave call performed yet) is unchanged by this refactor. 6 net new tests (13 renamed + 1 in `test_search_provider.py` + 5 in `test_search_provider_registry.py`, minus the 13 deleted from the old `test_search_client.py`). Full-suite run: 997 total, 979 passing, 1 skipped, 17 failed — the 15 already-tracked `test_text_to_speech.py` failures plus **two** flaky system tests this time (`test_full_level2_acceptance_scripted_conversation`, `test_level4_part_a_full_acceptance_scenario`) — both confirmed passing standalone together (5/5) immediately after, and neither depends on anything this refactor touched (`internet/`, `config/`, `docs/`, `pyproject.toml`, `requirements.txt` only). Consistent with, and further corroborating, every prior sprint's own conclusion this session that these are non-deterministic host-load flakes, not regressions — a different combination of the same known-flaky system tests has now failed on 3 of this session's last 4 full-suite runs, never the same combination twice, always clean standalone. `ruff check .` clean.

`ResearchEngine`/`Summarizer` still have no live caller — this revision changes nothing about that; Sprint 4.18 remains next.

### Post-Sprint Fix (2026-08-01, Sprint 4.20 — Integration Testing & Level Freeze, Part B)

`BraveSearchProvider.search()`'s own response parsing (`payload.get("web", {}).get("results", [])`) ran OUTSIDE the try/except that wraps the HTTP request/response handling — `payload.get("web", {})` only falls back to `{}` when the `"web"` key is genuinely absent; a real (if malformed/degraded) response shaped `{"web": null, ...}` makes it return `None` instead, and `.get(...)` on that `None` raised a raw, un-promised `AttributeError` rather than the `SearchError` this method's own docstring already guarantees ("never a raw requests exception"). Found during Sprint 4.20's own adversarial re-read of every `scheduler/`/`internet/` source file — confirmed as a real, reproducible gap (not theoretical) via a direct interactive check before fixing anything. Already masked in practice by `ResearchEngine.research()`'s own broad `except Exception` around its call to `search_provider.search()`, so no user-facing behavior was ever actually broken by this — but that's defense in depth hiding a real contract violation in this class's own code, not a reason to leave it unfixed. Fixed by moving the parsing inside the same try block. 2 new regression tests (`test_search_handles_a_null_web_value_gracefully`, `test_search_handles_a_null_results_value_gracefully`) in `tests/unit/internet/test_brave_search_provider.py`. See `backlog/technical_debt.md` item 32 and `sprint_4_20.md`'s own Sprint Completion Report.
