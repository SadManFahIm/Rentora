"""STT provider abstraction.

Defines the contract that backend agent logic depends on.
The actual browser-based implementation lives in
``frontend/src/lib/sttAdapter.ts`` and is loaded via the
``get_stt_provider()`` factory.

Backend providers (Google, AssemblyAI, Azure) can be plugged in
later without changing the agent core.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


class STTProvider(ABC):
    """Speech-to-text provider interface.

    The agent core calls ``transcribe(audio_base64, language)`` and
    receives normalized text.  The actual implementation can be:
    - Browser Web Speech API (client-side, MVP)
    - Third-party vendor (server-side, future)
    """

    @abstractmethod
    def transcribe(self, audio_base64: str, language: str = "en") -> str:
        """Transcribe base64-encoded audio returning normalized text."""
        raise NotImplementedError


class STTProviderError(RuntimeError):
    """Raised when an STT provider fails."""
