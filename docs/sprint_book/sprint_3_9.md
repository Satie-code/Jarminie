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
