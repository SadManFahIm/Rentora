"""TTS provider adapter using the Web Speech API ``speechSynthesis``.

Plugs into the ``get_tts_provider()`` factory.  Pure client-side —
nothing is recorded or uploaded.  Voice selection prefers Bangla (bn /
bn-BD), falling back to the browser default.

Architecture (per spec):
  Grounded Agent Response
  → TTS Provider (Web Speech API)
  → Audio Response
"""

from __future__ import annotations


class BrowserTTSAdapter:
    """Browser speechSynthesis — client-side only, no audio retained.

    Architecture (per spec):
      Grounded Agent Response
      → TTS Provider
      → Audio Response

    Supported languages: Bangla (bn / bn-BD), English (en / en-US).
    Voice selection prefers a Bangla voice when available; otherwise
    the browser default is used.
    """

    def speak(self, text: str, language: str = "en") -> None:
        """Synthesize speech from the given text.

        Args:
            text: The grounded agent response to speak.
            language: BCP-47 language tag.  ``"en"`` or ``"bn"`` are
                supported; other values are passed through to the browser.
        """
        # The actual TTS implementation lives in the frontend hook
        # ``useSpeechOutput``.  This adapter exists to satisfy the
        # provider interface contract.
        pass
