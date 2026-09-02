import { useCallback, useEffect, useRef, useState } from "react";

export type VoiceStatus =
  "idle" | "listening" | "processing" | "unsupported" | "denied" | "error" | "interim";

export type VoiceLanguage = "en" | "bn" | "en-bn" | "bn-en" | "bn-BD";

interface VoiceSearchOptions {
  /** BCP-47 language for recognition. Defaults to "bn-BD" (Bangla). */
  lang?: VoiceLanguage;
  /** Called with the final transcript once recognition completes. */
  onTranscript?: (transcript: string, language: string) => void;
  /** Called with interim results while speaking. */
  onInterim?: (transcript: string) => void;
}

/**
 * Bangla + English + Banglish voice input via the browser Web Speech API.
 *
 * - No audio is stored or uploaded — only the transcript is handed back.
 * - The microphone is purely additive: if the API is unsupported, denied or
 *   errors, the hook reports a state and text search keeps working.
 * - `lang` supports: "en", "bn", "en-bn" (Banglish), "bn-en" (Bangla-prefixed).
 * - `continuous: false` — one utterance per start/stop cycle (turn-based).
 */
export function useVoiceInput({
  lang = "bn-BD",
  onTranscript,
  onInterim,
}: VoiceSearchOptions = {}) {
  const [status, setStatus] = useState<VoiceStatus>("idle");
  const [supported, isSupported] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    const w = window as unknown as Record<string, unknown>;
    const Ctor = w.SpeechRecognition ?? w.webkitSpeechRecognition ?? w.msSpeechRecognition;
    return typeof Ctor === "function";
  });

  // Use a relaxed ref type since SpeechRecognition may not be available in all envs.
  const recognitionRef = useRef<WindowSpeechRecognition | null>(null);
  const onTranscriptRef = useRef(onTranscript);
  const onInterimRef = useRef(onInterim);
  onTranscriptRef.current = onTranscript;
  onInterimRef.current = onInterim;

  // Map the user-friendly language tag to a Web Speech API BCP-47 code.
  const langRef = useRef<string>(lang);
  langRef.current = lang;

  const langBCP47 = useCallback(() => {
    const l = langRef.current;
    const map: Record<string, string> = {
      en: "en-US",
      "en-US": "en-US",
      bn: "bn-BD",
      "bn-BD": "bn-BD",
      "en-bn": "en-BD", // Banglish-friendly
      "bn-en": "bn-BD", // Bangla-preferred
    };
    return map[l] || "en-US";
  }, []);

  const stop = useCallback(() => {
    recognitionRef.current?.abort();
    recognitionRef.current = null;
    setStatus("idle");
  }, []);

  const start = useCallback(() => {
    if (!isSupported) {
      setStatus("unsupported");
      return;
    }
    if (recognitionRef.current) {
      recognitionRef.current.abort();
      recognitionRef.current = null;
    }
    try {
      const Ctor =
        window.SpeechRecognition ?? window.webkitSpeechRecognition ?? window.msSpeechRecognition;
      const recognition = new (Ctor as any)();
      recognition.lang = langBCP47();
      recognition.interimResults = false;
      recognition.maxAlternatives = 1;
      recognition.continuous = false;

      recognition.onresult = (event: any) => {
        const result = event.results[0];
        const transcript = result?.[0]?.transcript?.trim() ?? "";
        if (transcript) {
          setStatus("processing");
          onTranscriptRef.current?.(transcript, langBCP47());
        }
      };

      recognition.onerror = (event: any) => {
        recognitionRef.current = null;
        const err = event.error;
        if (err === "not-allowed" || err === "service-not-allowed") {
          setStatus("denied");
        } else {
          setStatus("error");
        }
      };

      recognition.onend = () => {
        recognitionRef.current = null;
        // Return to idle unless we were in a continuous loop.
        setStatus((s) => (s === "processing" ? s : "idle"));
      };

      recognitionRef.current = recognition;
      setStatus("listening");
      recognition.start();
    } catch {
      recognitionRef.current = null;
      setStatus("error");
    }
  }, [isSupported, langBCP47]);

  // Cleanup on unmount so a dangling recognition session never leaks.
  useEffect(() => stop, [stop]);

  return { supported, status, start, stop, lang };
}

type WindowSpeechRecognition =
  | typeof window.SpeechRecognition
  | typeof window.webkitSpeechRecognition
  | typeof window.msSpeechRecognition;

// Extend Window type to include SpeechRecognition properties for TypeScript.
declare global {
  interface Window {
    SpeechRecognition: any;
    webkitSpeechRecognition: any;
    msSpeechRecognition: any;
  }
}
