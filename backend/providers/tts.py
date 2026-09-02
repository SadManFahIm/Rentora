"""TTS provider abstraction.

Defines the contract that the agent logic depends on.
The actual browser-based implementation lives in
``frontend/src/lib/ttsAdapter.ts``.

Backend providers (OpenAI, Azure, etc.) can be plugged in later
without changing the agent core.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


class TTSProvider(ABC):
    """Text-to-speech provider interface.

    The agent core calls ``speak(text, language)`` to synthesize
    speech from a grounded response.  The actual implementation can be:
    - Browser Web Speech API ``speechSynthesis`` (client-side, MVP)
    - Third-party vendor (server-side, future)
    """

    @abstractmethod
    def speak(self, text: str, language: str = "en") -> None:
        """Synthesize speech from the given text."""
        raise NotImplementedError


class TTSProviderError(RuntimeError):
    """Raised when a TTS provider fails."""
