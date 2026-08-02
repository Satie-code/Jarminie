"""VoicePersonalityModulator (Sprint 5.11 — Level 5 Part A).

Makes Jarvis and Minie sound different in *behavior*, not only via the
two distinct Coqui speaker IDs already configured since Sprint 2.4 — the
brief's own explicit instruction: "Natural pacing. Do not rely solely on
different TTS voices. Behavior should also differ."

**Text-level shaping, not a new TTS engine or model.** `voice/text_to_speech.py`'s
own docstring is explicit: `CoquiTextToSpeech`/`TextToSpeech` own
"synthesis and playback only... zero knowledge that Jarvis/Minie exist."
This module respects that boundary completely — `voice/text_to_speech.py`
is not modified. `shape_pacing()` sits between `Persona.compose_reply()`'s
already-tone-adapted output (Sprint 5.4) and the existing
`TextToSpeech.speak()` call, inserting pacing pauses at sentence/clause
boundaries, weighted by `PresentationState.voice_warmth` (5.5) — Jarvis's
own low-warmth baseline yields tighter, more clipped pacing; Minie's
higher baseline yields warmer, more spaced-out pacing.

**`pacing_pause_marker`'s real nature, verified not guessed**: Coqui's
own installed text-processing pipeline (`TTS.tts.utils.text.cleaners`,
version 0.27.5 as installed in this project) has no dedicated SSML-style
pause/silence token — punctuation characters (comma, period, etc.) are
simply part of the model's own supported character vocabulary and are
what actually produce audible pauses during synthesis, not a special
recognized marker. The default value (`"..."`, an ellipsis) is exactly
three such ordinary, already-supported punctuation characters in a
row — a real, working pacing technique, correctly described here as
such rather than as a dedicated pause API Coqui doesn't actually have.

**Core contract, structurally checkable**: `shape_pacing()` only ever
*inserts* `pacing_pause_marker` substrings — it never alters a word of
the actual text. Removing every inserted `f"{pacing_pause_marker} "`
substring from the output reconstructs the original input exactly,
byte-for-byte. This is the brief's own "Presentation never changes
intelligence" guarantee, made mechanically testable rather than merely
asserted in prose.
"""

import re

from config.schema import PresentationConfig
from presentation.presentation_state import clamp

_BOUNDARY_PATTERN = re.compile(r"([.!?,;:])(\s+)")
"""Matches a sentence/clause-ending punctuation character immediately
followed by whitespace — a real, existing boundary in the input text.
Deliberately requires trailing whitespace (not just the punctuation
itself) so a marker is only ever inserted *between* two chunks of text,
never appended after the very last sentence with nothing following it."""


class VoicePersonalityModulator:
    """Constructor DI per 03_Engineering_Standards.md: receives
    PresentationConfig only. No persona knowledge — a caller passes
    voice_warmth explicitly, keeping this a pure text transform, the
    same "pure decision function, no collaborator references" shape
    GestureEngine (5.9) already established."""

    def __init__(self, presentation_config: PresentationConfig) -> None:
        self._config = presentation_config

    def shape_pacing(self, text: str, voice_warmth: float) -> str:
        """Never raises. Empty text returns empty text unchanged. Finds
        every existing sentence/clause boundary in text, then inserts
        pacing_pause_marker at a subset of them — the fraction chosen
        interpolated between pacing_low_warmth_pause_weight (voice_warmth
        0.0) and pacing_high_warmth_pause_weight (voice_warmth 1.0)."""
        if not text:
            return text

        warmth = clamp(voice_warmth, 0.0, 1.0)
        weight = self._config.pacing_low_warmth_pause_weight + warmth * (
            self._config.pacing_high_warmth_pause_weight
            - self._config.pacing_low_warmth_pause_weight
        )
        matches = list(_BOUNDARY_PATTERN.finditer(text))
        if not matches or weight <= 0:
            return text

        step = max(1, round(1 / weight))
        insert_at = set(range(0, len(matches), step))

        pieces: list[str] = []
        cursor = 0
        for index, match in enumerate(matches):
            pieces.append(text[cursor : match.end()])
            cursor = match.end()
            if index in insert_at:
                pieces.append(f"{self._config.pacing_pause_marker} ")
        pieces.append(text[cursor:])
        return "".join(pieces)
