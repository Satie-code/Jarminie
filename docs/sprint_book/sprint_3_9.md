# Sprint 3.9 — Memory Retrieval Engine

## Sprint ID

3.9

## Sprint Name

Memory Retrieval Engine

## Purpose

Implement the Decision Engine pipeline's third stage, per [02_System_Architecture.md](../02_System_Architecture.md): *"Intent Detection → Context Analysis → **Memory Retrieval** → Priority Evaluation → Authority Evaluation → Engine Selection."* Composes across every memory layer built in Sprints 3.1–3.6 into one ranked, explainable query, so the rest of the Decision Engine can reason with relevant history in hand.

## Engineering Rationale

This sprint exists to close a real gap between [sprint_book/INDEX.md](INDEX.md)'s original roadmap-granularity Level 3 plan and Part 2's own architecture. That roadmap listed Intent Detection, Context Analysis, Priority Queue, and Authority Evaluation as the Decision Engine's four sprints — but Part 2's pipeline diagram names **five** stages after Context Analysis and before Authority Evaluation is reached, with "Memory Retrieval" as its own explicit step. This Sprint Book adds the sprint that diagram already implied. See this file's own place in the numbering and `sprint_book/INDEX.md`'s Level 3 breakdown note for the full before/after comparison.

Sprint 3.1's `MemoryStore.semantic_search()` and Sprint 3.2's `PersonaScopedMemory.recall_for_persona()` already satisfy Phase 3.1's "Retrieval accurate" acceptance criterion — but only *per type*, in isolation. Nothing yet combines Shared+Persona memory, Event memory, and Short-Term memory into one query, and nothing yet accounts for the fact that a highly-relevant but low-confidence Short-Term memory should not automatically outrank a highly-confident Long-term memory at similar semantic similarity — that requires blending Sprint 3.1's similarity scores with Sprint 3.5's confidence scores, a genuinely new piece of ranking logic that does not belong inside any single memory-type wrapper (Single Responsibility: a type-specific store should not need to know about cross-type ranking policy). This sprint is that composition layer, and nothing else — it introduces no new storage, no new confidence logic, only retrieval composition and ranking.

Every result this sprint returns carries its own `retrieval_reason` — a short, human-readable justification (similarity + confidence band) — specifically because Sprint 3.11's Authority Evaluation must produce an explainable decision trace, and "why was this memory even considered" is part of that explanation. Building this into the retrieval result now, rather than reconstructing it later from raw scores, keeps the Explainability Rule's obligation close to where the ranking decision is actually made.

## Objectives

- A `MemoryRetrievalEngine` that queries Shared+Persona memory (3.2), Event memory (3.3), and session-scoped Short-Term memory (3.4) in one call, given a query and the active persona.
- A combined ranking that blends semantic similarity with confidence score, config-weighted.
- Every result carries a human-readable `retrieval_reason` for downstream explainability.
- Never crosses the persona read-scoping boundary already enforced structurally by `PersonaScopedMemory` (3.2).

## Dependencies

3.1 (Memory Store Foundation), 3.2 (Shared & Persona Memory), 3.3 (Event Memory), 3.4 (Short-Term Memory), 3.5 (Confidence Scoring Engine), 3.6 (Memory Lifecycle Manager)

## Files to Create

- `memory/retrieval_engine.py` — `RetrievedMemory` (dataclass), `MemoryRetrievalEngine`.
- `tests/unit/memory/test_retrieval_engine.py`

## Files to Modify

- `config/schema.py` — extend `MemoryConfig`: `retrieval_similarity_weight: float = 0.6`, `retrieval_confidence_weight: float = 0.4` (validated to sum to `1.0`, same pattern as Sprint 3.5's scoring weights), `max_retrieval_results: int = 5`.
- `config/defaults.yaml` — updated to match.

## Expected Classes

- `RetrievedMemory` (dataclass) — `record: MemoryRecord`, `similarity_score: float` (0–1, Chroma distance normalized), `confidence_score: float` (0–100, from `record.confidence_score` at query time), `combined_rank_score: float`, `retrieval_reason: str` (e.g. `"82% similar · Long-term confidence (78/100)"`).
- `MemoryRetrievalEngine` — constructor DI: `(persona_scoped_memory: PersonaScopedMemory, event_memory: EventMemory, short_term_memory: ShortTermMemory, confidence_scorer: ConfidenceScorer, memory_config: MemoryConfig)`. Plain class — composition over already-`ManagedModule`-owned dependencies, same reasoning as `ContextManager` (2.8) not needing its own lifecycle.

## Expected Interfaces

None new — depends entirely on Sprints 3.1–3.6's existing interfaces.

## Expected Functions

- `MemoryRetrievalEngine.retrieve(query_text: str, persona_name: str, session_id: str, max_results: int | None = None) -> list[RetrievedMemory]` — queries `persona_scoped_memory.recall_for_persona(persona_name, query_text)`, `event_memory.search_milestones(query_text)`, and `short_term_memory.active_context_memories(session_id)` filtered by relevance to `query_text`; wraps every result as a `RetrievedMemory` with `combined_rank_score = (similarity_score * retrieval_similarity_weight) + (confidence_score / 100 * retrieval_confidence_weight)`; sorts descending; truncates to `max_results` (defaulting to `memory_config.max_retrieval_results`).
- `MemoryRetrievalEngine._build_retrieval_reason(similarity: float, confidence: float, band: ConfidenceBand) -> str` — internal, produces the human-readable justification string from a similarity score, a confidence score, and its band (via `confidence_scorer.band()`).

## Data Flow

```
ContextAnalysis.primary_topic (3.8) + active persona_name + session_id
      ↓
MemoryRetrievalEngine.retrieve(query_text, persona_name, session_id)
      ↓                    ↓                          ↓
PersonaScopedMemory   EventMemory.search_       ShortTermMemory.active_
.recall_for_persona   milestones(query_text)    context_memories(session_id)
      ↓                    ↓                          ↓
                  merged MemoryRecord candidates
      ↓
per-candidate: combined_rank_score = f(similarity, confidence)   (via ConfidenceScorer.band())
      ↓
sorted, truncated list[RetrievedMemory]  (each carrying retrieval_reason)
      ↓
Sprint 3.10 (Priority Queue) / Sprint 3.11 (Authority Evaluation & Engine Selection)
```

## Implementation Tasks

1. `config/schema.py` — `MemoryConfig` additions, weight-sum validation; `config/defaults.yaml` updated.
2. `memory/retrieval_engine.py` — `RetrievedMemory`, `MemoryRetrievalEngine.retrieve()`, `_build_retrieval_reason()`.
3. Unit tests, including the weight-blend ranking test described in Acceptance Criteria.

## Architecture Notes

`MemoryRetrievalEngine` is the first module in this Sprint Book to depend on *four* other Level 3 modules at once — an intentional, late composition point, not a sign of poor decomposition: it exists specifically so nothing upstream of it (3.2, 3.3, 3.4) needs to know about cross-type ranking, and nothing downstream of it (3.10, 3.11) needs to know which memory type a given result came from. It never queries `MemoryStore` (3.1) directly — always through the type-specific wrappers, preserving every scoping/permanence guarantee those sprints already built rather than re-implementing or bypassing them.

## Integration Considerations

- No live caller exists yet — wired into the real turn-processing path by Sprint 3.12, consuming `ContextAnalysis.primary_topic` (3.8) as its query text.
- Sprint 3.11's `DecisionTrace` includes each `RetrievedMemory.retrieval_reason` verbatim in its explanation — this sprint's output format is chosen with that direct downstream consumer in mind.
- Sprint 3.13 hardens the case where one of the three underlying queries fails (e.g. Chroma degraded per Sprint 3.1's Potential Risks) — this sprint's own scope is the happy-path composition only.

## Potential Risks

- **Weight tuning (0.6/0.4) is a guess**, same caveat as Sprint 3.5's scoring weights — config-driven for exactly that reason.
- **Merging three differently-shaped queries (semantic, semantic, recency-filtered) into one ranked list conflates "how well retrieved" with "how confident stored"** — the `retrieval_reason` string exists specifically to make this blend legible rather than a black box, but a future sprint may find the single scalar `combined_rank_score` insufficiently expressive for real explainability needs; flagged as a Future Consideration rather than over-built now.
- **No caching** — `retrieve()` re-queries all three sources on every call; acceptable at current conversation volume, revisit only if Sprint 3.14 shows a real latency problem (no premature optimization).

## Acceptance Criteria

- `retrieve()` never returns a memory outside the calling persona's read-scope (delegates to, and preserves, Sprint 3.2's structural guarantee).
- A ranking test proves the blend actually blends: a high-confidence, lower-similarity record outranks a low-confidence, higher-similarity one at one configured weight pair, and the ranking flips at a different weight pair — proving `combined_rank_score` is not silently just one field renamed.
- Every returned `RetrievedMemory.retrieval_reason` is a non-empty, human-readable string containing both a similarity and a confidence reference.
- Results are correctly truncated to `max_results`.
- `Event` and `Short-Term` results only appear when actually relevant to `query_text` — an unrelated query returns an empty list from those sources rather than irrelevant milestones/context.

## Testing Checklist

- [ ] Unit: cross-persona leak test (delegated guarantee still holds through this composition layer).
- [ ] Unit: weight-blend ranking test (both directions, as described in Acceptance Criteria).
- [ ] Unit: `retrieval_reason` content correctness for a few fixed similarity/confidence/band combinations.
- [ ] Unit: `max_results` truncation boundary.
- [ ] Unit: an empty/no-match query returns an empty list, not an error.
- [ ] Unit: `MemoryConfig` weight-sum validation (accepts 1.0, rejects mismatched pairs).

## Documentation Checklist

- [ ] `memory/retrieval_engine.py` docstring: explicit statement of this sprint's purpose as the pipeline's "Memory Retrieval" stage (per Part 2's diagram), and the similarity/confidence blend formula.
- [ ] `docs/STATUS.md` — Phase 3.3 (Decision Engine) row remains `Designing`.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md).

## Estimated Complexity

Medium-High.

## Estimated Development Time

1.5–2 days.

## Next Sprint

3.10 — Priority Queue.

## Future Considerations

- If `combined_rank_score`'s single-scalar blend proves insufficient for real explainability needs during Sprint 3.14 or later real use, consider a richer, multi-field ranking explanation — not built speculatively now.
- A retrieval result cache keyed by `(persona_name, session_id, query_text)` — only if Sprint 3.14's real-world verification shows retrieval latency is a genuine, measured problem.

---

## Sprint Completion Report (2026-07-18)

### Summary

Implemented `memory/retrieval_engine.py` (`RetrievedMemory`, `MemoryRetrievalEngine`) plus the three new `MemoryConfig` fields. Also added two small, additive (non-breaking) methods to Sprints 3.2/3.3's already-shipped classes — `PersonaScopedMemory.recall_for_persona_scored()` and `EventMemory.search_milestones_scored()` — a real, necessary gap found while implementing this sprint, not a deviation from it (see Engineering Decisions). 484/484 tests passing (460 prior + 24 new), `ruff check .` clean.

### Files Created

- `memory/retrieval_engine.py` — `RetrievedMemory` (dataclass), `MemoryRetrievalEngine`.
- `tests/unit/memory/test_retrieval_engine.py` — 21 tests.

### Files Modified

- `config/schema.py` — `MemoryConfig.retrieval_similarity_weight: float = 0.6`, `retrieval_confidence_weight: float = 0.4` (validated to sum to 1.0, mirroring Sprint 3.5's five-weight pattern), `max_retrieval_results: int = 5` (validated positive).
- `config/defaults.yaml` — `memory:` section extended to match.
- `memory/persona_scoped_memory.py` — added `recall_for_persona_scored()` (keeps Chroma distance); `recall_for_persona()` now delegates to it, unchanged behavior/signature. Added `_merge_by_distance_scored()`; `_merge_by_distance()` now delegates to it, unchanged behavior/signature/tests.
- `memory/event_memory.py` — added `search_milestones_scored()` (keeps Chroma distance); `search_milestones()` now delegates to it, unchanged behavior/signature.
- `tests/unit/memory/test_persona_scoped_memory.py` — 2 new tests for the scored variant.
- `tests/unit/memory/test_event_memory.py` — 1 new test for the scored variant.
- `docs/STATUS.md` — Phase 3.3 (Decision Engine) row's descriptive text updated; status itself deliberately left at `Designing`, per this sprint's own Documentation Checklist.

### Tests Added

24 total. In `test_retrieval_engine.py` (fake `PersonaScopedMemory`/`EventMemory`/`ShortTermMemory`, but a REAL `ConfidenceScorer` — it's pure and cheap, same precedent `test_lifecycle_manager.py` established in Sprint 3.6): delegation/no-cross-persona-leak through the composition layer; the weight-blend ranking test proving `combined_rank_score` genuinely blends (a high-confidence/lower-similarity record outranks a low-confidence/higher-similarity one at one weight pair, flipping at another); `retrieval_reason` content correctness across all five `ConfidenceBand`s; `max_results` truncation from both the config default and an explicit override; an empty/whitespace-only query short-circuiting before querying anything; Event Memory results below `_MIN_EVENT_SIMILARITY` being excluded (and included above it); Short-Term Memory results with zero keyword overlap being excluded (and included with overlap); and `MemoryConfig`'s new weight-sum/positivity validation. In `test_persona_scoped_memory.py`/`test_event_memory.py`: the new scored variants return real distance values, and produce the same underlying records (by id — see Engineering Decisions) as their existing unscored counterparts.

### Documentation Updated

This file (Sprint Completion Report). `memory/retrieval_engine.py`'s module docstring (pipeline-stage purpose, the similarity/confidence blend formula, and both implementation-time relevance-filtering decisions below). `memory/persona_scoped_memory.py`/`memory/event_memory.py` docstrings for the new scored methods. `docs/STATUS.md` as above.

### Acceptance Criteria Checklist

- ✔ `retrieve()` never returns a memory outside the calling persona's read-scope — delegates entirely to `recall_for_persona_scored()` (itself unchanged scoping logic from Sprint 3.2), verified by a test proving no result appears beyond what the fake `PersonaScopedMemory` itself returned.
- ✔ Weight-blend ranking test proves the blend genuinely blends, in both directions (confidence-heavy weights rank the high-confidence record first; similarity-heavy weights flip it).
- ✔ Every `RetrievedMemory.retrieval_reason` is a non-empty string containing both a similarity percentage and a confidence-band reference, verified across all five bands.
- ✔ Results correctly truncate to `max_results` (config default and explicit override).
- ✔ Event and Short-Term results only appear when relevant to `query_text` — verified for both inclusion and exclusion cases against real thresholds/heuristics (also confirmed against real embeddings, not just fakes; see Remaining Risks).

### Engineering Decisions

- **Added `recall_for_persona_scored()`/`search_milestones_scored()` to Sprints 3.2/3.3's already-shipped classes, purely additively.** `MemoryStore.semantic_search()`'s own docstring (written during Sprint 3.1's Post-Sprint Fix) explicitly names this exact need: "Distance is exposed... specifically so a caller combining results from more than one MemoryType/collection (`PersonaScopedMemory.recall_for_persona()`, Sprint 3.2; **the future `MemoryRetrievalEngine`, Sprint 3.9**) can genuinely rank the merged set by similarity" — but `recall_for_persona()`/`search_milestones()` as actually shipped both discard that distance before returning. Rather than changing either method's existing return type (which would have broken 7 existing tests across the two files and retroactively invalidated Sprint 3.2/3.3's own Acceptance Criteria Checklists), each gained a new sibling method that keeps distance, with the original method refactored to delegate to it — zero behavior change for any existing caller/test, full data available for this sprint. `_merge_by_distance()` (3.2) is preserved unchanged by the same pattern (delegates to a new `_merge_by_distance_scored()`), so its own dedicated direct unit test needed no changes either.
- **Chroma distance -> similarity_score via `1/(1+distance)`**, not a linear min-max normalization, because Chroma's default distance metric has no fixed, documented upper bound to normalize against. Empirically measured against the real embedding model while implementing this sprint: related content scored roughly 0.58-0.67 similarity, unrelated content roughly 0.32-0.36 — informs `_MIN_EVENT_SIMILARITY = 0.4` below.
- **Two relevance-filtering mechanisms not spelled out by the spec, both needed to satisfy "Event and Short-Term results only appear when actually relevant to query_text"**: (1) Event Memory results below `_MIN_EVENT_SIMILARITY` (0.4) are dropped — a semantic search always returns its nearest neighbors regardless of true relevance, so a cutoff is required for an unrelated query to ever yield an empty Event result set; (2) Short-Term Memory has no semantic search of its own at all (`active_context_memories()` is a plain per-session recency query), so relevance is approximated by a crude keyword-overlap fraction between `query_text` and each candidate's content — the same "keyword heuristic, real NLU not available at this point in the build order" discipline already established by `PersonaManager.detect_context_heuristic()` (2.11) and `ShortTermMemory.promote_from_turn()`'s own salience triggers (3.4).
- **Persona-scoped (Shared/Jarvis/Minie) results are NOT filtered by either mechanism** — the Acceptance Criteria names only Event and Short-Term as needing to vanish for an unrelated query; Persona/Shared memory is treated as core conversational background that should still surface even at low relevance, not a "bonus" recall.
- **Real bug found and fixed during real-model verification (not by any unit test)**: `_build_retrieval_reason()` initially used a Unicode middle-dot ("·") separator, matching this sprint's own spec example text verbatim — but printing it revealed the exact same Windows-console mojibake failure mode Sprint 1.6 already found and fixed for an em-dash (`docs/sprint_book/sprint_1_6.md`), which established sticking to ASCII in every runtime log/display string. Fixed by switching to a plain "-" before this sprint's own tests were finalized (no test asserted on the specific separator character, so no test needed updating). **Generalizable reminder**: this is the second time a spec's own prose example used a non-ASCII character that shouldn't be copied literally into runtime code — worth checking for on any future sprint whose spec includes a literal example string.

### Remaining Risks

- **Confirmed via real, non-mocked verification** against a real `MemoryStore` (temp SQLite + temp Chroma, real embeddings — no mocking of the embedding pipeline at all): stored a mix of Jarvis/Shared/Event/Short-Term records, then ran four real queries. A relevant technical query correctly ranked the matching Jarvis record highest; a degree-related query correctly surfaced the Event milestone (48% similarity, above the 0.4 threshold) while an unrelated query correctly excluded it; a hiking-related query correctly surfaced the Short-Term memory via keyword overlap while unrelated queries correctly excluded it; Persona/Shared results appeared even for a completely unrelated "pizza toppings" query, exactly as designed. This exceeds this sprint's own committed scope (Chroma/embedding realism wasn't required by the Testing Checklist, which is fakes-only) but was done given how central the similarity-normalization and relevance-threshold decisions are to this sprint's correctness.
- **`_MIN_EVENT_SIMILARITY` (0.4) and the Short-Term keyword-overlap approach are both implementation-time tuning guesses**, same caveat class as the sprint's own flagged 0.6/0.4 blend weights — informed by one real empirical measurement (see Engineering Decisions) but not extensively tuned. Config-driven for the blend weights; the two relevance mechanisms themselves are NOT config-driven (no field was added for either), since the spec's own Files to Modify list only named the three weight/limit fields — worth revisiting if Sprint 3.14 finds either threshold wrong in practice.
- This sprint's own flagged risks stand as expected: no caching (acceptable at current volume), and `combined_rank_score`'s single-scalar blend may prove insufficient for richer explainability later (both explicitly deferred, not built speculatively).
- `backlog/technical_debt.md` item 16 (shipped `ollama_model` default) doesn't apply here — this sprint has no Ollama/LLM dependency at all.

### Technical Debt

None new. The `recall_for_persona_scored()`/`search_milestones_scored()` additions are documented as Engineering Decisions above rather than technical debt, since they're a clean, permanent, non-breaking design (not a shortcut requiring future resolution).

### Recommendations

- **For Sprint 3.10 (Priority Queue)**: consumes `list[RetrievedMemory]` — worth double-checking its actual spec's assumptions about this sprint's output shape before implementing, per the established "check the next sprint's assumptions against what actually shipped" pattern (see Sprint 3.6's own Recommendations for the precedent).
- **For Sprint 3.11 (Authority Evaluation)**: `retrieval_reason` strings are ready to be included verbatim in a `DecisionTrace`, per this sprint's own Integration Considerations — no further formatting work anticipated.
- **`_MIN_EVENT_SIMILARITY` and the Short-Term relevance heuristic** are reasonable candidates for `MemoryConfig` fields if Sprint 3.14's real-world verification shows either needs per-deployment tuning — not added speculatively now, consistent with this sprint's own "no premature optimization" Potential Risk.

**Sprint 3.9 (Memory Retrieval Engine) is complete.** **Sprint 3.10 (Priority Queue) is next.**
