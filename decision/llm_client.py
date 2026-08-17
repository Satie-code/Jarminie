"""Language model access for the Decision Engine.

LanguageModelClient is a Protocol (Interface First Design,
03_Engineering_Standards.md) specifically so IntentDetector (this sprint)
and Sprint 3.8's Context Analysis never depend on the ollama package
directly — a future model-runtime swap (Part 3: "the architecture must
remain model-independent") only requires a new implementation of this
one method, not changes to either caller.

OllamaClient wraps every real failure mode the ollama Python client can
raise (confirmed empirically against a running Ollama instance while
implementing this sprint) into LlmError, never a raw library exception:
ollama.ResponseError (e.g. an unpulled model), a bare ConnectionError
(the client's own unreachable-host check), and httpx's own timeout
exceptions when a call exceeds timeout_seconds. Constructing a fresh
ollama.Client per call (rather than one long-lived client) is what makes
a genuinely per-call timeout_seconds possible — ollama.Client.generate()
itself has no per-call timeout parameter, only a constructor-level one.

is_reachable() is deliberately NOT part of the LanguageModelClient
Protocol above — the Protocol stays exactly one method, per the Sprint
Book's own explicit "deliberately minimal" constraint. It is an extra,
optional capability on this concrete class only; IntentDetector.start()
looks it up defensively (getattr, calls it only if present) so a fake
client used in tests needs no such method at all. This is what lets
start() perform a real "lightweight readiness check... not a full
generation call" (the Sprint Book's own wording) without widening the
shared interface every future LanguageModelClient implementation would
otherwise have to satisfy.

Sprint 3.13 (Error Handling & Recovery Hardening) named its own expected
new function `OllamaClient.check_readiness() -> bool` — by the time 3.13
was implemented, is_reachable() above already existed (built in Sprint
3.7, for exactly this same "cheap connectivity probe used at startup,
not on every generate() call" purpose) and IntentDetector.start()/
ContextAnalyzer.start() were already calling it defensively. Adding a
second, differently-named method with identical behavior would be pure
duplication, not hardening, so 3.13 reused is_reachable() as-is rather
than introducing a redundant check_readiness(). See sprint_3_13.md's own
completion report for the full reasoning.
"""

from typing import Protocol

from config.schema import ModelConfig
from core.logging_setup import get_logger

logger = get_logger(__name__)


class LlmError(Exception):
    """Raised for any language model call failure — connection, timeout,
    or an unpulled/unknown model. Never a raw ollama/httpx exception."""


class LanguageModelClient(Protocol):
    """A single-method contract, deliberately minimal to avoid
    over-fitting to Ollama's own client shape (ManagedModule's own
    "kept deliberately minimal" precedent, Sprint 1.5).

    stop (0.4.3 addition — real, measured latency finding): an optional
    list of stop sequences the model should halt generation at, once it
    reaches one. Defaulted to None (generate everything, the original
    behavior) so this stays additive — every pre-existing caller/fake
    needs no change unless it wants to opt in. Added after a real,
    reproducible finding against a live Ollama instance: IntentDetector/
    ContextAnalyzer's own "respond with exactly N lines and nothing
    else" prompt instructions are not reliably honored by llama3 — the
    model correctly emits the requested structured lines, then keeps
    generating an entire unsolicited extra paragraph afterward, which
    _parse_response() already discards. That wasted generation measured
    as roughly two-thirds of ContextAnalyzer's own real per-call latency
    (~10s of a ~15s call). A real stop sequence is the correct fix (an
    even stronger prompt instruction was already tried first per the
    user's own explicit preference and did not reliably work) — the
    blank line the model inserts between its own structured answer and
    its own unsolicited rambling ("\\n\\n") is the real, empirically
    observed boundary, not a guess."""

    def generate(
        self, prompt: str, timeout_seconds: float, stop: list[str] | None = None
    ) -> str: ...


class OllamaClient:
    """LanguageModelClient implementation against the real ollama
    Python client. Holds no persistent connection — start()/stop() on
    IntentDetector only manage a lightweight readiness check, not a
    connection lifecycle, since ollama.Client itself is a thin per-call
    HTTP wrapper with nothing to open or close."""

    def __init__(self, model_config: ModelConfig) -> None:
        self._model = model_config.ollama_model
        self._host = model_config.ollama_host

    def is_reachable(self) -> bool:
        """Cheap readiness probe (lists models, does not load one) —
        used by IntentDetector.start(), not by generate()."""
        import ollama

        try:
            ollama.Client(host=self._host, timeout=5).list()
            return True
        except Exception:
            logger.warning("Ollama host %s is not reachable.", self._host)
            return False

    def generate(
        self, prompt: str, timeout_seconds: float, stop: list[str] | None = None
    ) -> str:
        """Raises LlmError on timeout, connection failure, or an
        unpulled model — never a raw ollama/httpx exception, per
        Interface First Design keeping implementation-specific errors
        out of caller code. stop (0.4.3) is passed through to Ollama's
        own real stop-sequence support (options={"stop": [...]}) — a
        real, server-side generation control, not prompt-text advice
        the model can choose to ignore."""
        import ollama

        try:
            client = ollama.Client(host=self._host, timeout=timeout_seconds)
            options = {"stop": stop} if stop else None
            response = client.generate(
                model=self._model, prompt=prompt, stream=False, options=options
            )
            # Sprint 6.19 hardening (backlog item 33): .response access
            # moved inside this same try block, not after it — the
            # identical shape of gap item 32 already fixed for
            # BraveSearchProvider.search() (internet/brave_search_
            # provider.py). A malformed/unexpected response object's own
            # missing .response attribute would otherwise raise a raw
            # AttributeError this method's own docstring already
            # promises never to leak.
            return response.response
        except Exception as exc:
            raise LlmError(
                f"Ollama generate() failed for model {self._model!r}: {exc}"
            ) from exc
