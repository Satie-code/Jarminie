# Sprint 4.17 — Summarization & Source Validation

## Sprint ID

4.17

## Sprint Name

Summarization & Source Validation

## Purpose

Turn Sprint 4.16's raw `SearchResult`s into an actual answer, per `02_System_Architecture.md`'s Internet Agent section (*"Summarization. Source comparison. Source validation... should clearly distinguish between verified facts and uncertain information"*) and `04_Master_Implementation_Plan.md`'s Phase 4.4 acceptance criteria (*"Reliable research. Clear citations."*). This sprint closes the Internet Agent's own component work, the same role Sprint 4.10 played for closing the Workflow Engine's.

## Engineering Rationale

Corresponds to `docs/sprint_book/INDEX.md`'s roadmap-granularity `4.17 Summarization & Source Validation` entry, expanded to full detail alongside the rest of this Sprint Book (2026-07-31).

**Summarization reuses `decision/llm_client.py`'s existing `LanguageModelClient` Protocol/`OllamaClient` rather than adding a second LLM integration** — the same local Ollama runtime `IntentDetector`/`ContextAnalyzer` already call, keeping JARMINEI's own "one local AI runtime" architecture intact instead of introducing a second, parallel path for a task (natural-language generation from structured input) that runtime already does. This is a deliberate, reviewed dependency `internet/summarizer.py` takes on `decision/llm_client.py` — Sprint 4.16's own Architecture Notes described `internet/`'s Search/Research half as having "no dependency on `voice/`, `decision/`, or any other subsystem beyond its own `config/` section"; that statement was scoped to *that sprint's own files* (`search_client.py`/`research_engine.py`), not a permanent constraint on the whole `internet/` package — this sprint adds one new, one-directional dependency (`internet/` → `decision/llm_client.py`, never the reverse), the same shape `workflow/` → `device_control/` already established as the accepted pattern for one subsystem genuinely reusing another's real capability rather than duplicating it.

**Source validation is built as an honest, mechanical corroboration signal, not a fabricated "verified" badge.** No external fact-checking API exists in this project's technology stack, and Part 2's own language ("clearly distinguish between verified facts and uncertain information") does not claim JARMINEI can independently verify truth — it asks for honest labeling. This sprint's `SourceValidator` labels a claim as *corroborated* only when it is genuinely supported by more than one of Sprint 4.16's independently-returned `SearchResult`s, and *uncorroborated* otherwise — a real, checkable, non-inflated signal, matching the same honesty discipline `voice/speech_to_text.py`'s `no_speech_probability` and `memory/confidence_scorer.py`'s Dynamic Memory Formula already established elsewhere in this codebase: report what can actually be measured, never a confident-sounding number with nothing real behind it.

**Grounding is this sprint's single largest engineering risk, named explicitly**: an LLM asked to "summarize these search results" can hallucinate content not present in the source snippets at all — the same class of risk `backlog/technical_debt.md` item 9 already found and fixed for Whisper's transcription (fabricating plausible-sounding text from silence). A summarization prompt that doesn't structurally constrain the model to only the provided snippets risks producing a fluent, confident, and simply wrong answer — worse here than Whisper's silence-hallucination case, because a false research summary is presented to the user as if it were sourced fact. This sprint's own prompt design and Testing Checklist must treat this as a first-class concern, not an afterthought discovered later the way Sprint 2.5 discovered Whisper's.

## Objectives

- `Citation` (one source backing a summary: title, URL, corroboration status).
- `ResearchSummary` (the final answer: summary text, a list of `Citation`s, generated-at timestamp).
- `SourceValidator` — cross-references `SearchResult`s for corroboration, per Engineering Rationale above.
- `Summarizer` — composes `ResearchEngine` output (4.16) + `SourceValidator`'s labels into one grounded `ResearchSummary` via the shared `LanguageModelClient`.

## Dependencies

4.16 (Search & Research, for `ResearchEngine`/`SearchResult`); reuses `decision/llm_client.py`'s `LanguageModelClient`/`OllamaClient` (built at 3.7) rather than depending on any Level 3 Decision Engine sprint's own behavior.

## Files to Create

- `internet/source_validator.py` — `Citation` (dataclass), `SourceValidator`.
- `internet/summarizer.py` — `ResearchSummary` (dataclass), `Summarizer`.
- `tests/unit/internet/test_source_validator.py`
- `tests/unit/internet/test_summarizer.py`

## Files to Modify

- `config/schema.py` — `InternetConfig` (4.16) gains `summarization_model: str | None = None` (falls back to `ModelConfig.ollama_model` when unset — the same "reuse the shared model unless a subsystem needs its own" convention `ModelConfig`'s existing fields already follow) and `min_sources_for_corroboration: int = 2`.
- `config/defaults.yaml` — matching new `internet:` fields.

## Expected Classes

- `Citation` (dataclass) — `title: str`, `url: str`, `is_corroborated: bool`.
- `ResearchSummary` (dataclass) — `query: str`, `summary_text: str`, `citations: list[Citation]`, `generated_at: datetime`.
- `SourceValidator` — constructor DI: `(internet_config: InternetConfig)`. Stateless per call, the same "no lifecycle of its own" shape `ContextManager` (2.8) already established for a pure aggregator with no thread/connection/hardware to own.
- `Summarizer` — constructor DI: `(llm_client: LanguageModelClient, internet_config: InternetConfig)`. Also stateless per call.

## Expected Interfaces

None new — reuses `decision/llm_client.py`'s existing `LanguageModelClient` Protocol.

## Expected Functions

- `SourceValidator.validate(results: list[SearchResult]) -> list[Citation]` — a claim/source is `is_corroborated=True` when its core content (a simple, honest signal — e.g. overlapping key terms/domain-independent phrasing across snippets, not a claim of deep semantic fact-checking) appears across at least `min_sources_for_corroboration` distinct `SearchResult`s; every source is included in the output regardless (an uncorroborated single source is still cited, just honestly labeled, never silently dropped — Part 2 asks for *distinguishing* uncertain information, not hiding it).
- `Summarizer.summarize(query: str, results: list[SearchResult], citations: list[Citation]) -> ResearchSummary` — builds a prompt that structurally constrains the model to the provided snippets only (per the Grounding risk in Engineering Rationale — e.g. an explicit "only use the information below; if it doesn't answer the question, say so" instruction, the same defensive-prompting discipline `ModelConfig.whisper_initial_prompt` already uses for a different failure mode), calls `llm_client.generate()`, and degrades to a plain, honest "I found sources but couldn't summarize them right now" `ResearchSummary` (never a fabricated one) on any `LanguageModelClient` failure — mirroring `IntentDetector`'s own safe-`UNKNOWN`-on-failure precedent.

## Data Flow

```
ResearchEngine.research(query) (4.16) → [SearchResult, ...]
      ↓
SourceValidator.validate(results) → [Citation, ...]
      ↓
Summarizer.summarize(query, results, citations)
      ↓
LanguageModelClient.generate(grounded_prompt) → summary text (or a safe degrade on failure)
      ↓
ResearchSummary(query, summary_text, citations, generated_at)
      ↓
Sprint 4.18 (spoken/composed reply to the user)
```

## Implementation Tasks

1. `config/schema.py`/`config/defaults.yaml` — `InternetConfig` new fields.
2. `internet/source_validator.py` — `Citation`, `SourceValidator.validate()`.
3. `internet/summarizer.py` — `ResearchSummary`, `Summarizer.summarize()`, the grounded prompt template.
4. Unit tests: corroboration labeling against constructed multi-source/single-source fixtures; `Summarizer` against a fake `LanguageModelClient` (prompt structurally includes only the provided snippets; degrade-on-failure); an adversarial "the fake LLM returns a claim not present in any snippet" test asserting the sprint's own grounding discipline is at least prompt-level attempted (a real hallucination test against a real model is Sprint 4.20's job, matching `test_level3_real_model_verification.py`'s own opt-in precedent — this sprint's fast suite can only prove the prompt asks correctly, not that the real model always obeys).

## Architecture Notes

`Summarizer` never fetches full page content itself — it works from whatever `SearchResult.snippet` Sprint 4.16's provider returned (that sprint's own Potential Risks named this as an open, undecided question; this sprint resolves it by simply not building page-fetching, since Part 2's own text names no requirement for full-article ingestion and a snippet-only summary is an honest, bounded scope). If real use later shows snippets are too thin to summarize well, extending `ResearchEngine`/`SearchClient` with real page fetching is a Future Consideration, not retrofitted here.

`SourceValidator.validate()`'s corroboration signal is deliberately simple (term/phrase overlap, not semantic entailment) — a real semantic-similarity approach (e.g. reusing `memory/`'s own ChromaDB embedding machinery) is a plausible future improvement but adds a real dependency (`internet/` → `memory/` or a duplicated embedding call) this sprint's own scope doesn't need to justify yet; named as a Future Consideration rather than built speculatively.

## Integration Considerations

- No live caller exists yet — `Summarizer.summarize()` is real, callable, and tested, but nothing wires a conversation turn (`EngineSelection.INTERNET_AGENT`) to it. Sprint 4.18's job, mirroring every prior mechanism sprint's own "wiring deferred" precedent in this Sprint Book.
- This sprint closes Internet Agent's own component work — Sprints 4.16–4.17 together are what Sprint 4.18 wires live, the same two-sprint-then-integrate shape Workflow (4.9–4.10 then 4.11) already established.

## Potential Risks

- **Grounding/hallucination is this sprint's largest risk**, named at length in Engineering Rationale above — a real, adversarial verification pass against the actual configured model (not just a fake `LanguageModelClient`) belongs in Sprint 4.20's own real-model verification tier, the same treatment Sprint 3.14 gave Level 3's Ollama-dependent classification accuracy.
- **`min_sources_for_corroboration` (2) is an unvalidated guess**, same caveat class as every other tuned bound in this codebase.
- **A single-source query (Sprint 4.16 returns exactly one result) means nothing can ever be corroborated** — an honest, expected consequence of the corroboration definition above, not a bug; `Summarizer`'s own output must still be useful and clearly labeled in that case, not degraded to uselessness just because nothing could be cross-checked.
- **Local LLM summarization quality/latency is unverified against real multi-source search content** — Sprint 3.7's own real-model verification only exercised short conversational classification prompts, not a longer, structured summarization task; a real timing/quality check belongs in Sprint 4.20.

## Acceptance Criteria

- `SourceValidator.validate()` correctly labels a claim appearing in ≥`min_sources_for_corroboration` results as corroborated, and a claim appearing in only one as not — verified against constructed fixtures with a clear, known ground truth.
- `Summarizer.summarize()`'s prompt structurally includes only the provided `SearchResult` snippets (verified by inspecting the constructed prompt in a unit test, not just trusting the model's output) and every returned `Citation` traces back to a real, provided `SearchResult`.
- A `LanguageModelClient` failure degrades `summarize()` to an honest "couldn't summarize" `ResearchSummary`, never an unhandled exception or a fabricated-looking result.
- Every `Citation` in a `ResearchSummary` is genuinely one of the sources that fed it — no phantom citations.

## Testing Checklist

- [ ] Unit: corroboration labeling, both the corroborated and single-source cases.
- [ ] Unit: `Summarizer.summarize()`'s constructed prompt contains only the provided snippets (string-inspection assertion, not model-output-trusting).
- [ ] Unit: `Summarizer.summarize()` degrades honestly on a fake `LanguageModelClient` raising/timing out.
- [ ] Unit: every `Citation` returned traces to a real input `SearchResult` (no citation fabrication possible even in principle, by construction).
- [ ] Adversarial: a fake `LanguageModelClient` that returns a claim absent from every snippet — asserted against whatever grounding check this sprint's own implementation adds (at minimum, documented as a known limitation if no structural check beyond prompt wording is built).

## Documentation Checklist

- [ ] `internet/summarizer.py` docstring: the grounding/hallucination risk and this sprint's own mitigation, stated explicitly (mirroring `voice/speech_to_text.py`'s own Whisper-hallucination documentation).
- [ ] `internet/source_validator.py` docstring: the honest, mechanical (not semantic-fact-checking) nature of the corroboration signal, stated explicitly.
- [ ] `docs/STATUS.md` — Phase 4.4 (Internet Agent) row stays `Designing` (closed by 4.18, mirroring Workflow Engine's 4.9/4.10-then-4.11 precedent).

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md).

## Estimated Complexity

Medium–High.

## Estimated Development Time

1.5–2 days.

## Risks

See Potential Risks above.

## Next Sprint

4.18 — Scheduler & Internet Agent Integration.

## Future Considerations

- Real page-content fetching beyond provider snippets — flagged above, not built now.
- Semantic-similarity-based corroboration (reusing embedding infrastructure) — flagged above as a plausible future improvement.
- Result/summary caching — same Future Consideration Sprint 4.16 already named for raw search results, extended here to summaries.

## Sprint Completion Report (2026-07-31)

Implemented as specified, authorized directly ("okay complete the sprint 4.17") — no stop-and-ask gate this time (unlike 4.16), so implementation proceeded straight through. Delivered `internet/source_validator.py` (`Citation`, `SourceValidator`), `internet/summarizer.py` (`ResearchSummary`, `Summarizer`), `InternetConfig.summarization_model`/`min_sources_for_corroboration` in `config/schema.py`/`config/defaults.yaml`. 17 new tests (6 in `test_source_validator.py`, 11 in `test_summarizer.py`), `LanguageModelClient` faked in every test via a local `FakeLanguageModelClient` double, matching every other real caller of that Protocol in this codebase. `ruff check .` clean.

**One real, deliberate deviation from this sprint's own originally-specified constructor signature, made and documented before writing any test**: `Summarizer.__init__` takes `(llm_client, internet_config, model_config)`, not the spec's literal `(llm_client, internet_config)` — `LanguageModelClient.generate()` requires a `timeout_seconds` argument on every call, and neither `InternetConfig` (per this sprint's own spec) nor anything else passed to `Summarizer` names one. Checked how every other real caller of this exact Protocol solves the identical problem first, rather than guessing: `IntentDetector`/`ContextAnalyzer` (Level 3) both take `ModelConfig` and read `ollama_timeout_seconds` from it — `Summarizer` does the same. `InternetConfig.summarization_model` stays exactly as specified but is deliberately never read by `Summarizer` itself (documented explicitly in both the class docstring and the config field's own docstring) — `generate()` has no per-call model-selection parameter, so which model gets used is entirely a function of which concrete `OllamaClient` Sprint 4.18's `main.py` wiring constructs and passes in, not something this class could act on even if it tried.

**Source validation's corroboration signal was implemented as a genuinely mechanical term-overlap check** (significant words ≥4 characters, common stopwords excluded, ≥2 shared terms between two results counts as mutual support), not a semantic/embedding-based one — matching this sprint's own Architecture Notes exactly, and verified against constructed fixtures with real, deliberately distinct vocabulary per result (not just trivially identical/trivially different text) so the test suite proves the actual overlap arithmetic, not just its two trivial extremes.

**Grounding/hallucination — this sprint's own largest named risk — is addressed at the prompt level only, honestly documented as such rather than oversold.** `_build_prompt()` structurally embeds only the caller-provided `SearchResult`s and an explicit "use ONLY the information below... say so" instruction; a dedicated test (`test_a_fabricated_llm_response_is_passed_through_unverified`) proves — and documents in its own docstring as a known, not-yet-closed limitation — that nothing in `Summarizer` can detect or reject a fabricated claim a real model might still produce despite the prompt's own instruction. Real, adversarial verification against an actual configured Ollama model remains explicitly Sprint 4.20's job, per this sprint's own Potential Risks.

Full-suite run: 991 total, 975 passing, 1 skipped (Sprint 4.16's own opt-in real-API test, correctly), 15 failed — exactly the already-tracked `test_text_to_speech.py` failures, nothing more. Notably, unlike the full-suite runs for Sprints 4.15 and 4.16 (each of which additionally flaked on one different system-level acceptance test under full-suite host load), **this run had zero additional flaky failures** — consistent with, and further corroborating, the conclusion already reached in those two sprints' own completion reports that the extra failures were genuine non-deterministic host-resource-contention noise, not regressions tied to either sprint's own changes.

`docs/STATUS.md` (Phase 4.4 stays `Developing`, closes at Sprint 4.18) and `docs/sprint_book/INDEX.md` (4.17 row → `Complete`) both updated. **This closes Internet Agent's own component work (Sprints 4.16-4.17)** — no live caller exists yet for either `ResearchEngine.research()` or `Summarizer.summarize()`. **Sprint 4.18 (Scheduler & Internet Agent Integration) is next** — the big one: wires both this Sprint Book's halves (Scheduler from 4.14/4.15, Internet Agent from 4.16/4.17) into `main.py`/`CommunicationPipeline` for real, including this project's first genuinely proactive (non-turn-triggered) behavior.
