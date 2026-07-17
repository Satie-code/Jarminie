"""Voice-layer error hierarchy.

Every Level 2 (Communication) module raises a subclass of VoiceError rather
than a bare exception, mirroring the config/errors.py pattern established
in Sprint 1.2. Each later voice sprint (Wake Word, Speech-to-Text,
Text-to-Speech, Voice Session Manager, Conversation Session Store) adds its
own subclass here rather than starting a parallel error hierarchy — see
docs/sprint_book/sprint_2_1.md.
"""


class VoiceError(Exception):
    """Base class for any Voice Engine failure."""


class MicrophoneError(VoiceError):
    """Raised for microphone device, stream, or mode-gating failures."""


class WakeWordError(VoiceError):
    """Raised for wake-word engine load or detection failures."""


class SpeechToTextError(VoiceError):
    """Raised for speech-to-text model load or transcription failures."""


class TextToSpeechError(VoiceError):
    """Raised for text-to-speech model load, synthesis, or playback failures."""


class SessionError(VoiceError):
    """Raised for voice session lifecycle failures."""
