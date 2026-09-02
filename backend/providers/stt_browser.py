"""STT provider adapter using the Web Speech API.

Plugs into the ``get_stt_provider()`` factory.  No audio is stored or
uploaded — only the transcript is returned.  Supports Bangla (bn-BD),
English (en-US), and mixed Bangla+English input.

This is a Python adapter that conforms to the ``STTProvider`` interface.
The actual Web Speech API recognition happens in the frontend hook
``useVoiceInput.ts``; this adapter exists so the backend agent logic
remains vendor-agnostic.

Architecture (per spec):
  Audio
  → STT Provider (Web Speech API, frontend)
  → normalised text
  → Rental Agent
"""

from __future__ import annotations

from ..providers import STTProvider, STTProviderError


class BrowserSTTAdapter(STTProvider):
    """Web Speech API — client-side only, no audio retained.

    Note: The actual speech recognition event and transcript extraction
    is handled by the frontend ``useVoiceInput`` hook.  This adapter
    exists to satisfy the provider interface contract so the agent
    logic does not need to know whether STT is server-side or client-side.
    """

    def transcribe(self, audio_base64: str, language: str = "en") -> str:
        # MVP: do not attempt to decode base64 audio here.
        # The frontend useVoiceInput hook handles recognition natively.
        raise STTProviderError(
            "BrowserSTT: use the frontend useVoiceInput hook for transcription. "
            "Raw-audio base64 transcription is not implemented in the MVP. "
            "Call startListening() from the hook and receive the transcript "
            "as plain text."
        )
