"""Provider abstractions for STT, TTS, and LLM.

Each provider implements a small, focused interface.  Configuration is
driven by environment variables so that production credentials never
hard-code into source control.

Examples
--------
# .env
STT_PROVIDER=browser
TTS_PROVIDER=browser
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


# ---------------------------------------------------------------------------
# Speech-to-Text
# ---------------------------------------------------------------------------


class STTProvider(ABC):
    """Speech-to-text provider interface.

    The actual transcription can be implemented client-side (e.g. Web Speech
    API) or by a third-party vendor.  The backend defines the contract; the
    frontend provides the browser-based adapter.
    """

    @abstractmethod
    def transcribe(self, audio_base64: str, language: str = "en") -> str:
        """Transcribe base64-encoded audio returning normalized text.

        Intended for server-side providers.  Client-side STT happens in the
        frontend hook ``useVoiceSearch`` and returns plain text directly;
        the backend abstraction exists so we can plug in Google/AssemblyAI/
        Azure later without changing the agent logic.
        """


class STTProviderError(RuntimeError):
    """Raised when an STT provider fails."""


def get_stt_provider() -> STTProvider:
    """Factory — returns the configured provider instance."""
    name = os.getenv("STT_PROVIDER", "browser").lower()
    if name == "browser":
        # Import lazily to avoid hard dependencies when not needed.
        from .stt_browser import BrowserSTTAdapter  # type: ignore

        return BrowserSTTAdapter()
    # Add more providers later (assemblyai, google, azure, etc.)
    raise STTProviderError(f"Unknown STT provider: {name}")


# ---------------------------------------------------------------------------
# Text-to-Speech
# ---------------------------------------------------------------------------


class TTSProvider(ABC):
    """Text-to-speech provider interface."""

    @abstractmethod
    def speak(self, text: str, language: str = "en") -> None:
        """Synthesize speech from text."""


class TTSProviderError(RuntimeError):
    """Raised when a TTS provider fails."""


def get_tts_provider() -> TTSProvider:
    """Factory — returns the configured provider instance."""
    name = os.getenv("TTS_PROVIDER", "browser").lower()
    if name == "browser":
        from .tts_browser import BrowserTTSAdapter  # type: ignore

        return BrowserTTSAdapter()
    # Add more providers later (openai, azure, etc.)
    raise TTSProviderError(f"Unknown TTS provider: {name}")


# ---------------------------------------------------------------------------
# Language normalisation for the Web Speech API
# ---------------------------------------------------------------------------

# Web Speech API BCP-47 language codes we support out of the box.
_STT_LANG_MAP: dict[str, str] = {
    "en": "en-US",
    "en-US": "en-US",
    "bn": "bn-BD",
    "bn-BD": "bn-BD",
    "en-bn": "en-BD",  # Banglish-friendly
    "bn-en": "bn-BD",  # Bangla-preferred
}


def normalize_stt_lang(lang: str) -> str:
    """Normalize a user-facing language tag to a Web Speech API code."""
    return _STT_LANG_MAP.get(lang, lang)


def stt_languages_supported() -> list[str]:
    """Return the list of language tags we normalize for STT."""
    return list(_STT_LANG_MAP.keys())
