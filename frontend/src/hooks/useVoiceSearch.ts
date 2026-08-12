import { useCallback, useEffect, useRef, useState } from "react";

export type VoiceSearchStatus =
  "idle" | "listening" | "processing" | "unsupported" | "denied" | "error";

interface SpeechRecognitionLike {
  lang: string;
  interimResults: boolean;
  maxAlternatives: number;
  continuous: boolean;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
}

interface VoiceSearchOptions {
  /** BCP-47 language for recognition. Defaults to bn-BD (Bangla). */
  lang?: string;
  /** Called with the final transcript once recognition completes. */
  onTranscript?: (transcript: string) => void;
}

function getSpeechRecognition(): (new () => SpeechRecognitionLike) | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as Record<string, unknown>;
  const Ctor = w.SpeechRecognition ?? w.webkitSpeechRecognition ?? w.msSpeechRecognition;
  return typeof Ctor === "function" ? (Ctor as new () => SpeechRecognitionLike) : null;
}

/**
 * Bangla voice search via the browser Web Speech API.
 *
 * - No audio is stored or uploaded — only the transcript is handed back.
 * - The microphone is purely additive: if the API is unsupported, denied or
 *   errors, the hook reports a state and text search keeps working.
 * - `lang` is configurable (defaults to bn-BD for Bangla/Banglish input).
 */
export function useVoiceSearch({ lang = "bn-BD", onTranscript }: VoiceSearchOptions = {}) {
  const [status, setStatus] = useState<VoiceSearchStatus>("idle");
  const [supported] = useState<boolean>(() => getSpeechRecognition() !== null);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const onTranscriptRef = useRef(onTranscript);
  onTranscriptRef.current = onTranscript;

  const stop = useCallback(() => {
    recognitionRef.current?.abort();
    recognitionRef.current = null;
    setStatus("idle");
  }, []);

  const start = useCallback(() => {
    const Ctor = getSpeechRecognition();
    if (!Ctor) {
      setStatus("unsupported");
      return;
    }
    if (recognitionRef.current) {
      recognitionRef.current.abort();
      recognitionRef.current = null;
    }
    try {
      const recognition = new Ctor();
      recognition.lang = lang;
      recognition.interimResults = false;
      recognition.maxAlternatives = 1;
      recognition.continuous = false;
      recognition.onresult = (event) => {
        const result = event.results[0];
        const transcript = result?.[0]?.transcript?.trim() ?? "";
        if (transcript) {
          setStatus("processing");
          onTranscriptRef.current?.(transcript);
        }
      };
      recognition.onerror = (event) => {
        recognitionRef.current = null;
        setStatus(
          event.error === "not-allowed" || event.error === "service-not-allowed"
            ? "denied"
            : "error"
        );
      };
      recognition.onend = () => {
        recognitionRef.current = null;
        // A successful result flips to "processing"; anything else returns to idle.
        setStatus((s) => (s === "processing" ? s : "idle"));
      };
      recognitionRef.current = recognition;
      setStatus("listening");
      recognition.start();
    } catch {
      recognitionRef.current = null;
      setStatus("error");
    }
  }, [lang]);

  // Cleanup on unmount so a dangling recognition session never leaks.
  useEffect(() => stop, [stop]);

  return { supported, status, start, stop };
}
