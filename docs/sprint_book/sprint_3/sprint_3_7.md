# Sprint 3.7 — Intent Detection

## Sprint ID

3.7

## Sprint Name

Intent Detection

## Purpose

Begin Phase 3.3 (Decision Engine) with its first pipeline stage, per [02_System_Architecture.md](../02_System_Architecture.md)'s Decision Engine diagram: *"Input → Intent Detection → Context Analysis → Memory Retrieval → Priority Evaluation → Authority Evaluation → Engine Selection → Execution → Response Generation."* Uses the Ollama runtime (`ModelConfig.ollama_model = "gemma3"`, reserved since Sprint 1.2) to classify what the user is actually asking for.

## Engineering Rationale

This is the first sprint in the entire project to perform real language *understanding* rather than deterministic logic or a keyword heuristic. Every prior placeholder that stood in for this — `Persona.compose_reply()`'s templated acknowledgement (Sprint 2.9), `PersonaManager.detect_context_heuristic()`'s keyword lists (Sprint 2.11) — was explicitly documented as provisional, waiting for exactly this sprint. That inheritance carries a real obligation: Reliability over Intelligence and the Fail Gracefully Rule apply *more* strictly here, not less, because an LLM call can fail in ways deterministic code cannot — the Ollama service can be down, the model can be unpulled, a call can hang. None of those failure modes may be allowed to hang or crash a live voice turn; per Interface First Design, this sprint introduces a `LanguageModelClient` protocol (concrete `OllamaClient` implementation) specifically so the failure-handling and prompt-construction logic in `IntentDetector` never depends on Ollama's concrete client library directly, and so a future model-runtime swap (Part 3: "the architecture must remain model-independent") doesn't ripple through this or Sprint 3.8.

`ModelConfig.ollama_model` has held the value `"gemma3"` since Sprint 1.2 specifically for this moment; this sprint is also the first real installation/verification of the `ollama` Python client and a running Ollama service, tracked in `backlog/technical_debt.md` item 1 ("Remaining: ... `ollama` (Phase 2.2/3.3)").

## Objectives

- A `LanguageModelClient` protocol and concrete `OllamaClient` implementation, shared by this sprint and Sprint 3.8.
- An `IntentDetector` that classifies a transcript + `ConversationContext` (2.8) into a structured `Intent`.
- A failure/timeout path that always degrades to a safe, low-confidence default intent — logged, never raised — rather than blocking a conversation turn.

## Dependencies

2.8 (Context Manager), Ollama runtime (external service, `ModelConfig.ollama_model`)

## Files to Create

- `decision/__init__.py`
- `decision/llm_client.py` — `LanguageModelClient` (Protocol), `OllamaClient`, `LlmError`.
- `decision/models.py` — `IntentCategory` (Enum), `Intent` (dataclass).
- `decision/intent_detector.py` — `IntentDetector(ManagedModule)`.
- `tests/unit/decision/test_llm_client.py`
- `tests/unit/decision/test_intent_detector.py`

## Files to Modify

- `config/schema.py` — extend `ModelConfig`: `ollama_host: str = "http://localhost:11434"`, `ollama_timeout_seconds: float = 10.0`. Add validation (non-empty host, positive timeout) to the existing config validation pass.
- `config/defaults.yaml` — updated to match.

## Expected Classes

- `IntentCategory` (Enum) — `INFORMATIONAL`, `ACTION_REQUEST`, `MEMORY_RECALL`, `EMOTIONAL_SUPPORT`, `EMERGENCY`, `CASUAL_CONVERSATION`, `UNKNOWN`. `UNKNOWN` is the universal safe-failure value — every degrade path in this sprint resolves here, never to a guessed category.
- `Intent` (dataclass) — `category: IntentCategory`, `confidence: float`, `raw_transcript: str`, `detected_at: datetime`.
- `LanguageModelClient` (Protocol) — `generate(prompt: str, timeout_seconds: float) -> str`. Deliberately minimal (one method), matching `ManagedModule`'s own "kept deliberately minimal to avoid over-fitting" precedent (Sprint 1.5).
- `OllamaClient` — constructor DI: `(model_config: ModelConfig)`. Implements `LanguageModelClient` against the real `ollama` Python client.
- `IntentDetector(ManagedModule)` — constructor DI: `(llm_client: LanguageModelClient, model_config: ModelConfig)`.

## Expected Interfaces

- `LanguageModelClient` (new, shared by 3.7/3.8) — see above.
- `ManagedModule` (reused) — `start()` performs a lightweight readiness check (not a full generation call) against the configured Ollama host; `stop()` is a no-op beyond logging (the `ollama` client holds no persistent connection to close); `health_check()` reports the last-known reachability state, cheaply (no live network call on every check — a repeat of the pattern established for `WhisperSpeechToText`/`CoquiTextToSpeech`'s `_healthy` flag, Sprint 2.13).

## Expected Functions

- `OllamaClient.generate(prompt: str, timeout_seconds: float) -> str` — raises `LlmError` (never a raw library exception, per Interface First Design keeping implementation-specific errors out of caller code) on timeout, connection failure, or an unpullled model.
- `IntentDetector.detect(transcript: str, context: ConversationContext) -> Intent` — builds a prompt from `transcript` + `context.recent_turns`, calls `llm_client.generate()`, parses the response into an `IntentCategory` + confidence. Any `LlmError`, timeout, or unparseable response is caught and logged; the method returns `Intent(category=UNKNOWN, confidence=0.0, raw_transcript=transcript, detected_at=now())` in every such case — this method must never raise, matching `PersonaManager.compose_reply_safely()`'s established contract exactly.

## Data Flow

```
transcript (from VoiceSessionManager, 2.5) + ConversationContext (2.8)
      ↓
IntentDetector.detect(transcript, context)
      ↓
prompt construction (transcript + recent_turns)
      ↓
LanguageModelClient.generate(prompt, timeout_seconds)   →   OllamaClient   →   Ollama service
      ↓ (success)                                    ↓ (LlmError / timeout / bad parse)
response parsed into Intent                    Intent(category=UNKNOWN, confidence=0.0)
      ↓
Sprint 3.8's Context Analysis
```

## Implementation Tasks

1. `config/schema.py` — `ModelConfig` additions; `config/defaults.yaml` updated.
2. `decision/llm_client.py` — `LanguageModelClient` protocol, `OllamaClient`, `LlmError`.
3. `decision/models.py` — `IntentCategory`, `Intent`.
4. `decision/intent_detector.py` — `IntentDetector(ManagedModule)`, prompt construction, response parsing, the unconditional fail-safe-to-`UNKNOWN` path.
5. Unit tests against a **fake** `LanguageModelClient` (deterministic canned responses) for all classification-logic tests — the same "fakes at the hardware/ML boundary" convention established since Sprint 2.1 for Whisper/Coqui/openWakeWord. Real-model verification is explicitly out of this sprint's committed test suite; see Sprint 3.14.

## Architecture Notes

`decision/` is a new top-level package, matching [03_Engineering_Standards.md](../03_Engineering_Standards.md)'s Repository Structure, which already names it. `IntentDetector` depends on `ConversationContext` (2.8) but not on `Persona`/`PersonaManager` (2.9–2.11) — Intent Detection classifies *what* is being asked, independent of *which persona* is currently active; persona routing is Sprint 3.8's `suggested_persona` output, kept as a clean separation of concerns.

## Integration Considerations

- No live caller exists yet — wired into the real turn-processing path by Sprint 3.12, alongside Sprint 3.8.
- `Intent.category == EMERGENCY` has no real consequence until Sprint 3.10 (Priority Queue) and Sprint 3.11 (Authority Evaluation) exist to act on it — this sprint only classifies, it never triggers anything.
- The committed CI test suite never makes a real network call to Ollama (fakes only); a real, opt-in verification pass against a running Ollama instance is Sprint 3.14's job, mirroring exactly how Whisper/Coqui's real-model verification was kept separate from the fast committed suite throughout Level 2.

## Potential Risks

- **This is the project's first genuinely non-deterministic component** — the same LLM call can classify similar inputs differently across runs. Mitigated by the `UNKNOWN` fail-safe default and by keeping every *downstream* sprint (3.8–3.11) tolerant of an `UNKNOWN` intent rather than assuming classification is always correct (Reliability over Intelligence: the system must remain useful even when this stage is wrong).
- **Prompt design is not specified by the Engineering Specification** (Part 2 defines the pipeline stage, not prompt content) — this is a genuine implementation-time decision; whatever prompt template is chosen must be recorded in this file's eventual Sprint Completion Report, not left implicit in code.
- **`ollama_timeout_seconds` default (10s) is an untested guess** — real latency depends entirely on hardware and model size; config-driven specifically so Sprint 3.14's real-model verification can correct it without a code change.

## Acceptance Criteria

- `detect()` correctly classifies a fixed labeled test set of example transcripts into the expected `IntentCategory`, against a fake `LanguageModelClient`.
- A simulated `LlmError` (connection failure) from the client results in `Intent(category=UNKNOWN, confidence=0.0)`, logged, never raised.
- A simulated timeout behaves identically to a connection failure — no code path allows an unbounded wait.
- `IntentDetector.detect()` never raises for any input, including an empty transcript.

## Testing Checklist

- [ ] Unit: `detect()` classification correctness against a fixed labeled fixture set (fake client).
- [ ] Unit: `LlmError` from the client degrades to `UNKNOWN`, logged, not raised.
- [ ] Unit: timeout degrades to `UNKNOWN`, logged, not raised.
- [ ] Unit: an empty transcript does not raise.
- [ ] Unit: `OllamaClient.generate()` wraps a simulated underlying library exception into `LlmError`.
- [ ] Unit: `ModelConfig` new fields load with correct defaults and validate.

## Documentation Checklist

- [ ] `decision/intent_detector.py` docstring: the exact fail-safe contract ("never raises, degrades to UNKNOWN"), cross-referencing `PersonaManager.compose_reply_safely()`'s precedent.
- [ ] `decision/llm_client.py` docstring: records the Interface First rationale for `LanguageModelClient` existing as a protocol rather than depending on `OllamaClient` directly.
- [ ] `docs/STATUS.md` — Phase 3.3 (Decision Engine) row updated to `Designing`.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md).

## Estimated Complexity

High — the project's first LLM-integration sprint, with a genuinely new class of failure mode (model/service availability, non-determinism) that every prior sprint's testing conventions didn't need to address.

## Estimated Development Time

2–2.5 days.

## Next Sprint

3.8 — Context Analysis.

## Future Considerations

- If a second model runtime is ever needed (Part 3: "additional models can be integrated later without significant refactoring"), it implements `LanguageModelClient` directly — no change anticipated to `IntentDetector`'s own logic.
- Prompt-engineering iteration (improving real classification accuracy against real conversations) is expected to continue well past this sprint's initial ship — flagged as ongoing tuning, not a one-time deliverable.

---

## Sprint Completion Report (2026-07-18)

### Summary

Implemented `decision/models.py` (`IntentCategory`, `Intent`), `decision/llm_client.py` (`LanguageModelClient`, `LlmError`, `OllamaClient`), and `decision/intent_detector.py` (`IntentDetector(ManagedModule)`), plus the two new `ModelConfig` fields. This is the project's first sprint to perform real LLM-based language understanding and the first real installation/verification of the `ollama` Python client (`0.6.2`) and a running Ollama service — closing `backlog/technical_debt.md` item 1's last remaining Level-1-through-3 entry. 439/439 tests passing (405 prior + 34 new), `ruff check .` clean.

### Files Created

- `decision/models.py` — `IntentCategory` (Enum, 7 values incl. `UNKNOWN`), `Intent` (dataclass).
- `decision/llm_client.py` — `LlmError`, `LanguageModelClient` (Protocol), `OllamaClient`.
- `decision/intent_detector.py` — `IntentDetector(ManagedModule)`, prompt construction, response parsing.
- `tests/unit/decision/test_llm_client.py` — 7 tests.
- `tests/unit/decision/test_intent_detector.py` — 24 tests (incl. 2 parametrized cases: 6 labeled classifications, 3 confidence-clamping bounds).

### Files Modified

- `config/schema.py` — `ModelConfig.ollama_host: str = "http://localhost:11434"`, `ollama_timeout_seconds: float = 10.0`; validation added to `_validate_models()`.
- `config/defaults.yaml` — `models:` section extended to match.
- `tests/unit/config/test_schema.py` — 3 new tests for the two fields' defaults and validation.
- `docs/STATUS.md` — Phase 3.3 (Decision Engine) row updated to `Designing`.
- `docs/backlog/technical_debt.md` — item 1 updated (`ollama` now installed); new item 16 (see Remaining Risks).
- `requirements.txt` — unchanged; `ollama>=0.3` was already declared (reserved since an earlier sprint), only the venv install was outstanding.

### Tests Added

34 total, all against a fake `LanguageModelClient`/mocked `ollama.Client` — no real network call in the committed suite, per this sprint's own Testing Checklist. Covers: the full labeled classification set (6 categories, case-insensitive category names); `LlmError` and a simulated-timeout degradation to `UNKNOWN` (identical code path, both documented as such); an empty and a whitespace-only transcript short-circuiting without calling the client at all; a response missing `CATEGORY:`, an unrecognized category name, and unparseable/out-of-range confidence values (clamped to `[0, 1]`); the configured timeout being passed through; `health_check()`/`start()`/`stop()` including recovery-after-failure and degradation-after-failure of the `_healthy` flag; and `OllamaClient.generate()` wrapping an unpulled-model `ResponseError`-equivalent, a `ConnectionError`, and a timeout into `LlmError`, plus confirming a fresh `ollama.Client` is constructed per call with the given `timeout_seconds` (`ollama.Client.generate()` has no per-call timeout of its own).

### Documentation Updated

This file (Sprint Completion Report). `decision/intent_detector.py`'s module docstring (the fail-safe contract, prompt-design rationale). `decision/llm_client.py`'s module docstring (Interface First rationale, and why `is_reachable()` is deliberately NOT part of the `LanguageModelClient` Protocol). `docs/STATUS.md`, `docs/backlog/technical_debt.md` as above.

### Acceptance Criteria Checklist

- ✔ `detect()` correctly classifies a fixed labeled test set into the expected `IntentCategory`, against a fake client (6/6 in the parametrized fixture set; additionally confirmed against the real, running Ollama instance — see Remaining Risks/Recommendations).
- ✔ A simulated `LlmError` (connection failure) results in `Intent(UNKNOWN, 0.0)`, logged via `logger.warning(..., exc_info=True)`, never raised.
- ✔ A simulated timeout behaves identically — confirmed both at `IntentDetector` level (same `LlmError` path) and at `OllamaClient` level (a real timeout exception is wrapped into `LlmError`).
- ✔ `IntentDetector.detect()` never raises for any input, including an empty transcript (verified to short-circuit before any client call) and a malformed/unparseable LLM response.

### Engineering Decisions

- **`is_reachable()` kept off the `LanguageModelClient` Protocol.** The spec asks `start()` to perform "a lightweight readiness check (not a full generation call)," but the Protocol is explicitly "deliberately minimal (one method)." Resolved by adding `is_reachable()` only to the concrete `OllamaClient` (wraps a cheap `ollama.Client.list()` call, confirmed for real to not load any model), with `IntentDetector.start()` looking it up defensively via `getattr(..., None)` — a fake client implementing only `generate()` is still fully usable and defaults to "assumed reachable." This keeps the shared Protocol's shape exactly as specified while still giving `start()` a real network-based check.
- **`IntentDetector.start()` does not raise on an unreachable Ollama host**, unlike `WhisperSpeechToText`/`CoquiTextToSpeech`'s precedent of raising on a real load failure. Reasoning: those components genuinely cannot function without their loaded model; `IntentDetector.detect()` recovers per-call regardless of `start()`'s outcome (the `_healthy` flag flips back on the next successful call, same as Whisper's own recovery pattern) — marking the module `FAILED` at startup would only block `CoreManager`'s automatic recovery for a transient outage, since nothing currently calls `restart_module()` automatically (a known, still-open gap from `backlog/technical_debt.md`'s discussion in `sprint_2_13.md`).
- **Prompt format is plain two-line text** (`CATEGORY: ...` / `CONFIDENCE: ...`), not Ollama's JSON-schema-forcing `format=` parameter, specifically because using it would require widening `LanguageModelClient.generate()`'s signature beyond the Sprint Book's specified `(prompt, timeout_seconds) -> str` shape. Parsing is regex-based and defensive (missing category, unknown category name, and unparseable/out-of-range confidence all resolve to a safe default rather than raising).
- **Empty/whitespace-only transcripts short-circuit before any LLM call** — an efficiency improvement within the sprint's own scope (avoids a real, non-trivial-latency network call for a degenerate input that can only ever be `UNKNOWN` anyway), not a spec deviation.

### Remaining Risks

- **Confirmed via real, non-mocked verification** against an actually-running local Ollama instance (not just the fakes-based committed suite, which this sprint's own Testing Checklist explicitly scoped to fakes only): `IntentDetector` correctly classified all 6 of the same labeled sample categories used in the unit tests when run for real against `llama3:latest` (the model actually pulled on this machine), and correctly degraded to `UNKNOWN` with `health_check() == False` when pointed at an unreachable host, recovering to `UNKNOWN`-but-logged rather than raising. This exceeds this sprint's own committed scope (real verification was named as Sprint 3.14's job) but was done as an extra confidence check given how consequential this component is.
- **`ollama_timeout_seconds`'s 10-second default is confirmed too short for a cold model load** — real measurement during this sprint's own verification showed a cold `llama3:latest` load-and-generate taking ~53 seconds, dropping to ~2.8 seconds once warm. This matches the sprint's own flagged risk exactly ("an untested guess... real latency depends entirely on hardware and model size"); no code change made since Sprint 3.14 is the named place to correct it with real data, which this sprint's finding now supplies.
- **New: the shipped `ollama_model` default (`"gemma3"`) does not match what's actually pulled on this development machine (`llama3:latest`)** — `backlog/technical_debt.md` item 16. Does not block this sprint (fakes-only committed tests; real verification above used `llama3` explicitly, not the shipped default) but must be resolved — either by pulling `gemma3` or changing the default — before Sprint 3.14's real-model verification pass, which will otherwise fail immediately on a 404 model-not-found.
- This sprint's own flagged non-determinism risk stands as expected: the same transcript can plausibly classify differently across LLM calls. No downstream sprint (3.8+) exists yet to confirm tolerance of this in practice.

### Technical Debt

- **Item 1 updated**: `ollama` now installed (`0.6.2`), matching the version constraint (`>=0.3`) already declared in `requirements.txt`.
- **New item 16**: `ModelConfig.ollama_model` default (`"gemma3"`) vs. the actually-pulled local model (`llama3:latest`) — a user decision, not silently changed, per the same pattern as items 5 and 7 (wake-phrase and TTS-voice-ID gaps).

### Recommendations

- **Resolve `backlog/technical_debt.md` item 16 before Sprint 3.14** — pull `gemma3` (`ollama pull gemma3`) or change the default to `llama3`, whichever the user prefers; either is a one-line config change once decided.
- **For Sprint 3.8 (Context Analysis)**: reuses `LanguageModelClient`/`OllamaClient` as-is per this sprint's own design intent — no changes anticipated to either.
- **`ollama_timeout_seconds` should be revisited with the real cold/warm latency numbers above** once Sprint 3.14 (or any earlier real-model exercise) is ready to tune it; 10s comfortably covers a warm call but not a cold one.

**Sprint 3.7 (Intent Detection) is complete — Phase 3.3 (Decision Engine) is now `Designing`.** **Sprint 3.8 (Context Analysis) is next.**
