"""Response Generation — the Decision Engine pipeline's final stage
(02_System_Architecture.md: "... -> Engine Selection -> Execution ->
**Response Generation**"), built for real here after Sprint 3.12 had
deliberately left it as Persona.compose_reply()'s own fixed-template
acknowledgement ("compose_reply() IS the pipeline's Response Generation
stage at Level 3" — personas/base.py's own docstring, at the time). That
decision is reversed here at the user's explicit request: a live
conversational turn now gets a real, grounded, persona-toned answer
instead of a templated echo of the transcript.

Reuses decision/llm_client.py's existing LanguageModelClient Protocol/
OllamaClient rather than adding a second LLM integration — the exact
precedent internet/summarizer.py's Summarizer already established for
"one subsystem genuinely reusing another's real capability" (Sprint
4.17), applied here one stage earlier in the same pipeline that already
calls the same client for Intent Detection/Context Analysis.

generate() raises LlmError on failure rather than degrading to a safe
default of its own — unlike IntentDetector/ContextAnalyzer/Summarizer,
this class has no safe fallback text that belongs to it: the real
fallback is Persona.compose_reply()'s own template, which lives in
personas/, a module decision/ must not depend on (the same
one-directional dependency discipline Summarizer's own docstring
documents: "internet/ -> decision/llm_client.py... the identical shape
workflow/ -> device_control/ already established"; decision/ ->
personas/ would invert Persona's own documented dependency on
decision/authority.py's DecisionTrace). CommunicationPipeline — which
already depends on both decision/ and personas/ — is where the fallback
decision belongs; see voice/pipeline.py's _compose_conversational_reply().
"""

from config.schema import ModelConfig
from decision.authority import AuthorityLevel, DecisionTrace
from decision.llm_client import LanguageModelClient
from voice.context_manager import ConversationContext

_PERSONA_TONE: dict[str, str] = {
    "jarvis": "professional, logical, direct, and focused on getting things done",
    "minie": "warm, calm, caring, and conversational",
}
_DEFAULT_TONE = "helpful and conversational"
"""Small, local persona-tone constants — the same "small literal lookup,
not NLU" discipline this codebase already uses for _WORKFLOW_KEYWORDS/
_SCHEDULER_KEYWORDS (decision/authority.py). Kept here, not in
personas/, to preserve the one-directional decision/ -> (nothing in
personas/) dependency this module's own docstring explains."""

_AUTHORITY_GUIDANCE: dict[AuthorityLevel, str] = {
    AuthorityLevel.INFORM: "Answer plainly, as a simple statement of fact.",
    AuthorityLevel.RECOMMEND: (
        "Phrase your answer as a recommendation or suggestion, not a command."
    ),
    AuthorityLevel.EMERGENCY_ASSIST: (
        "You are authorized to assist directly with this. Say so plainly, then help."
    ),
}

_PROMPT_TEMPLATE = (
    "You are JARMINEI, a voice assistant currently speaking as {persona_name}, "
    "whose tone is {tone}.\n\n"
    "Recent conversation (oldest first):\n{turns_text}\n\n"
    "{memory_block}"
    "{authority_line}"
    'User\'s latest message: "{transcript}"\n\n'
    "Reply to the user directly, in your own words, as if speaking the reply aloud:\n"
    "- If you can answer the question or help with the request, do so concisely "
    "(1-3 sentences) — this reply will be read aloud by a text-to-speech engine.\n"
    "- If the request is ambiguous, or you're missing information you'd genuinely "
    "need to help, ask exactly one brief clarifying question instead of guessing.\n"
    "- Never invent specific facts, numbers, or details you don't actually know.\n"
    "Respond with ONLY the words to speak — no labels, no quotation marks, no stage "
    "directions."
)


class ResponseGenerator:
    """Constructor DI per 03_Engineering_Standards.md: receives the
    LanguageModelClient it calls and the ModelConfig it reads its call
    timeout from — the identical (llm_client, model_config) shape
    IntentDetector/ContextAnalyzer/Summarizer already use."""

    def __init__(self, llm_client: LanguageModelClient, model_config: ModelConfig) -> None:
        self._llm_client = llm_client
        self._timeout_seconds = model_config.ollama_timeout_seconds

    def generate(
        self,
        transcript: str,
        context: ConversationContext,
        decision_trace: DecisionTrace | None,
        persona_name: str,
    ) -> str:
        """Generate a real, persona-toned, context-grounded reply to one
        conversational turn. Raises LlmError on any call failure — see
        this module's own docstring for why the caller, not this class,
        owns the degrade-to-template fallback. decision_trace=None (the
        Decision Engine pipeline itself failed this turn) is tolerated:
        the prompt is built without trace-derived memory/authority
        grounding, the same tolerance Persona.compose_reply() already
        had."""
        prompt = _build_prompt(transcript, context, decision_trace, persona_name)
        return self._llm_client.generate(prompt, self._timeout_seconds).strip()


def _build_prompt(
    transcript: str,
    context: ConversationContext,
    decision_trace: DecisionTrace | None,
    persona_name: str,
) -> str:
    tone = _PERSONA_TONE.get(persona_name, _DEFAULT_TONE)

    if context.recent_turns:
        turns_text = "\n".join(
            f'User: "{turn.user_text}"\n{turn.persona_name}: "{turn.response_text}"'
            for turn in context.recent_turns
        )
    else:
        turns_text = "(no prior turns in this session)"

    memory_block = ""
    authority_line = ""
    if decision_trace is not None:
        if decision_trace.retrieved_memories:
            memories_text = "\n".join(
                f"- {memory.record.content}" for memory in decision_trace.retrieved_memories
            )
            memory_block = f"Relevant things you remember about the user:\n{memories_text}\n\n"
        guidance = _AUTHORITY_GUIDANCE.get(decision_trace.authority_level)
        if guidance:
            authority_line = f"{guidance}\n\n"

    return _PROMPT_TEMPLATE.format(
        persona_name=persona_name,
        tone=tone,
        turns_text=turns_text,
        memory_block=memory_block,
        authority_line=authority_line,
        transcript=transcript,
    )
