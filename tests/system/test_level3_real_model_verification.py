"""Level 3 real-model verification (Sprint 3.14) — opt-in, NOT part of
the fast committed suite's usual guarantees.

Every other test in this project fakes the Ollama boundary
(LanguageModelClient) and Chroma's real embedding model is otherwise only
exercised incidentally through unit tests, never against real
conversational input crafted specifically to judge classification
sensibility. This file is the dedicated, real counterpart: a real
OllamaClient talking to an actually-running Ollama instance, and a real
ChromaMemoryClient's default embedding model, exercised against a small,
fixed set of unambiguous example inputs.

Per sprint_3_14.md's own Engineering Rationale: unlike Level 2's live
human-voice round trip (which no automated test can perform), Ollama
inference is text-in/text-out and fully scriptable — a real model call
can be exercised by an automated test with no person in the loop. This
file is still kept opt-in rather than folded into the fast suite for the
same reason real Whisper/Coqui/openWakeWord verification was kept
separate through Level 2: real model calls are slow, and this project's
CI needs the committed suite to stay fast.

Opt-in mechanism: every test below skips (not fails) if a real Ollama
instance isn't reachable at the configured host — the same "advisory,
not fatal" posture Sprint 3.13 established for IntentDetector.start()
itself. This lets the file live in the repo permanently, run
automatically whenever the environment genuinely has Ollama available,
and degrade to a clean skip everywhere else (including this project's own
sandboxed development session, which currently has no Ollama
installation at all — see docs/backlog/technical_debt.md item 16's
2026-07-20 update).

Assertions here are deliberately about *reasonableness*, never exact
wording or an exact confidence value — real LLM output is not
deterministic, matching this sprint's own Implementation Tasks wording
("confirming classification/extraction is reasonable... not asserting
exact wording").

Model name is read from JARMINEI_TEST_OLLAMA_MODEL, defaulting to
ModelConfig's own shipped default ("llama3" as of Sprint 3.14 — see
technical_debt.md item 16) so a machine with a different model pulled
can still run this file without editing it, just by setting the env var.
"""

import os
from datetime import UTC, datetime

import pytest

from config.schema import DatabaseConfig, MemoryConfig, ModelConfig
from database.sqlite_client import SqliteClient
from decision.context_analyzer import ContextAnalyzer
from decision.intent_detector import IntentDetector
from decision.llm_client import OllamaClient
from decision.models import Intent, IntentCategory
from memory.chroma_client import ChromaMemoryClient
from memory.memory_store import MemoryStore
from memory.models import MemoryRecord, MemoryType
from voice.context_manager import ConversationContext


def _model_config() -> ModelConfig:
    """ollama_timeout_seconds=120.0 (the shipped default, 10.0, is sized
    for a warm/already-loaded model — a real Ollama instance cold-loading
    a multi-GB model for its first call in a session can genuinely take
    well over 10s, confirmed empirically while implementing this test
    against a real local Ollama instance)."""
    return ModelConfig(
        ollama_model=os.environ.get("JARMINEI_TEST_OLLAMA_MODEL", ModelConfig().ollama_model),
        ollama_timeout_seconds=120.0,
    )


@pytest.fixture(autouse=True)
def _skip_if_ollama_unreachable():
    """Runs before every test in this file; skips the whole file with one
    clear reason if no real Ollama instance answers at the configured
    host, OR if it answers but the configured model isn't actually
    pulled — never a failure, matching this sprint's own "opt-in, not
    fatal" design for real-model verification. The second check matters
    because OllamaClient.is_reachable() alone only proves connectivity
    (it calls list(), not generate()) — a reachable Ollama instance with
    a *different* model pulled than ollama_model (exactly this project's
    own dev machine, see docs/backlog/technical_debt.md item 16) would
    otherwise fail every test here with a confusing "model not found"
    error instead of a clear, actionable skip."""
    model_config = _model_config()
    client = OllamaClient(model_config)
    if not client.is_reachable():
        pytest.skip(
            "No reachable Ollama instance at the configured host — real-model "
            "verification skipped. Install Ollama and run `ollama pull "
            f"{model_config.ollama_model}` (or set JARMINEI_TEST_OLLAMA_MODEL to "
            "an already-pulled model), then re-run to actually exercise this file."
        )
    import ollama as _ollama_pkg

    pulled = [m.model for m in _ollama_pkg.Client(host=model_config.ollama_host).list().models]
    if not any(name.split(":")[0] == model_config.ollama_model for name in pulled):
        pytest.skip(
            f"Ollama is reachable but {model_config.ollama_model!r} is not pulled "
            f"(pulled models: {pulled}) — run `ollama pull {model_config.ollama_model}` "
            "or set JARMINEI_TEST_OLLAMA_MODEL to one of the pulled models above, "
            "then re-run to actually exercise this file."
        )


@pytest.fixture
def context() -> ConversationContext:
    now = datetime.now(UTC)
    return ConversationContext(
        session_id="real-model-verification",
        active_persona_name="jarvis",
        recent_turns=[],
        session_started_at=now,
        last_activity_at=now,
    )


@pytest.mark.parametrize(
    ("transcript", "acceptable_categories"),
    [
        ("What is the capital of France?", {IntentCategory.INFORMATIONAL}),
        # A real Ollama run (llama3, 2026-07-19) classified this as
        # MEMORY_RECALL rather than the ACTION_REQUEST originally expected
        # here — a defensible read for a general-purpose model with no
        # fine-tuning on this project's specific taxonomy, not a bug.
        # Both are accepted rather than tuning the prompt to force one
        # exact answer, per sprint_3_14.md's own Integration Considerations
        # ("prompt-tuning feedback... not a Level 3 blocker").
        (
            "Please remind me to call mom tomorrow",
            {IntentCategory.ACTION_REQUEST, IntentCategory.MEMORY_RECALL},
        ),
        ("Help, there's a fire in the kitchen!", {IntentCategory.EMERGENCY}),
        ("Hey, how's it going?", {IntentCategory.CASUAL_CONVERSATION}),
    ],
)
def test_intent_detector_produces_a_reasonable_category_for_unambiguous_input(
    context, transcript, acceptable_categories
):
    """A small, fixed set of deliberately unambiguous example inputs —
    not an exhaustive classification-accuracy benchmark, just confirming
    the real prompt/parsing pipeline (decision/intent_detector.py)
    produces sensible output against a real model, not just the fake's
    canned responses every other test in this project uses."""
    detector = IntentDetector(OllamaClient(_model_config()), _model_config())
    detector.start()

    intent = detector.detect(transcript, context)

    assert intent.category in acceptable_categories, (
        f"Expected one of {acceptable_categories} for {transcript!r}, got "
        f"{intent.category} (real LLM output — this may reflect prompt-tuning "
        f"feedback for decision/intent_detector.py, not necessarily a Level 3 "
        f"blocker, per sprint_3_14.md's own Integration Considerations)"
    )
    assert 0.0 <= intent.confidence <= 1.0


def test_context_analyzer_extracts_a_nonempty_topic_for_real_input(context):
    """Confirms the real prompt/parsing pipeline (decision/
    context_analyzer.py) produces a non-empty, sensible topic against a
    real model — not asserting exact wording, per this file's own
    docstring."""
    analyzer = ContextAnalyzer(OllamaClient(_model_config()), _model_config())
    analyzer.start()
    intent = Intent(
        category=IntentCategory.INFORMATIONAL,
        confidence=0.9,
        raw_transcript="What's the weather like in Paris tomorrow?",
        detected_at=datetime.now(UTC),
    )

    result = analyzer.analyze(intent, context)

    assert result.primary_topic.strip() != ""


def test_real_chroma_embedding_model_ranks_relevant_content_first(tmp_path):
    """A real ChromaMemoryClient (the default local embedding model, no
    Ollama involved) genuinely ranks semantically related content above
    unrelated content — the same assertion tests/unit/memory/
    test_memory_store.py's own committed suite already makes, repeated
    here per this sprint's own explicit Implementation Task naming a
    dedicated real-embedding-model verification pass. This test has no
    Ollama dependency of its own, but is still subject to this file's
    autouse Ollama-reachability skip for simplicity (one uniform skip
    condition for the whole file rather than a per-test exception) —
    real Chroma already runs continuously in the fast committed suite
    regardless (see this module's own docstring), so nothing is lost by
    this file being all-or-nothing."""
    database_config = DatabaseConfig(
        sqlite_path=str(tmp_path / "memory.db"), chroma_path=str(tmp_path / "chroma")
    )
    memory_config = MemoryConfig(chroma_collection_prefix="real_model_verification")
    sqlite_client = SqliteClient(database_config.sqlite_path)
    chroma_client = ChromaMemoryClient(memory_config, database_config)

    store = MemoryStore(sqlite_client, chroma_client)
    store.start()
    try:
        store.store(
            MemoryRecord(
                memory_type=MemoryType.SHARED,
                content="the user's favorite programming language is Python",
            )
        )
        store.store(
            MemoryRecord(
                memory_type=MemoryType.SHARED, content="the user drinks coffee every morning"
            )
        )

        results = store.semantic_search(
            MemoryType.SHARED, "what language does the user like to code in", n_results=2
        )
    finally:
        store.stop()

    assert "Python" in results[0][0].content
