import { useCallback, useEffect, useRef, useState } from "react";

export type SpeechStatus = "idle" | "speaking" | "unsupported" | "error";

interface SpeechSynthesisVoiceLike {
  lang: string;
  name: string;
  default: boolean;
}

/**
 * Browser text-to-speech for Copilot replies (Phase 15 — B3).
 *
 * - Pure client-side: `window.speechSynthesis` reads the text aloud, nothing
 *   is recorded or uploaded.
 * - Purely additive: unsupported browsers report `status: "unsupported"` and
 *   the UI keeps working.
 * - Voice selection prefers a Bangla (bn / bn-BD) voice when asked for one,
 *   falling back to the browser default otherwise.
 */
export function useSpeechOutput(lang = "bn-BD") {
  const [status, setStatus] = useState<SpeechStatus>("idle");
  const supported =
    typeof window !== "undefined" &&
    typeof window.speechSynthesis?.getVoices === "function" &&
    typeof window.SpeechSynthesisUtterance === "function";
  const statusRef = useRef(status);
  statusRef.current = status;

  const stop = useCallback(() => {
    if (typeof window === "undefined") return;
    window.speechSynthesis.cancel();
    setStatus("idle");
  }, []);

  const pickVoice = useCallback(
    (voices: SpeechSynthesisVoiceLike[]): SpeechSynthesisVoiceLike | null => {
      if (!voices.length) return null;
      const preferred = voices.find((v) => v.lang.toLowerCase().startsWith(lang.toLowerCase()));
      if (preferred) return preferred;
      if (lang.startsWith("bn")) {
        const anyBengali = voices.find((v) => v.lang.toLowerCase().startsWith("bn"));
        if (anyBengali) return anyBengali;
      }
      return null;
    },
    [lang]
  );

  const speak = useCallback(
    (text: string) => {
      if (!supported || !text.trim()) return;
      try {
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(text);
        const voices = window.speechSynthesis.getVoices();
        const voice = pickVoice(voices);
        if (voice) {
          utterance.lang = voice.lang;
          utterance.voice = voice as SpeechSynthesisVoice;
        } else {
          utterance.lang = lang;
        }
        utterance.rate = 0.95;
        utterance.onend = () => setStatus((s) => (s === "speaking" ? "idle" : s));
        utterance.onerror = () => setStatus((s) => (s === "speaking" ? "error" : s));
        setStatus("speaking");
        window.speechSynthesis.speak(utterance);
      } catch {
        setStatus("error");
      }
    },
    [supported, lang, pickVoice]
  );

  // Some browsers load voices asynchronously — warm the voice list on mount.
  useEffect(() => {
    if (typeof window === "undefined" || !supported) return;
    const load = () => window.speechSynthesis.getVoices();
    load();
    window.speechSynthesis.addEventListener?.("voiceschanged", load);
    return () => {
      window.speechSynthesis.cancel();
      window.speechSynthesis.removeEventListener?.("voiceschanged", load);
    };
  }, [supported]);

  return { supported, status, speak, stop };
}
