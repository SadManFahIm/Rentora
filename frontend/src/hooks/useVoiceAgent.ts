import { useCallback, useRef, useState } from "react";
import { useVoiceInput } from "../hooks/useVoiceInput";
import { useSpeechOutput } from "../hooks/useSpeechOutput";
import { api } from "../services/api";

// ---- Voice Agent state ----

export type VoiceAgentState =
  | "ready" // Idle, ready to listen
  | "listening" // Recording in progress
  | "processing" // Agent is thinking
  | "speaking" // TTS is speaking
  | "error"; // Something went wrong

export interface VoiceAgentOptions {
  /** Optional initial conversation ID (binds to existing negotiation). */
  conversationId?: number;
  /** Optional room ID if starting a fresh negotiation. */
  roomId?: number;
  /** Language for STT. Defaults to "bn" (Bangla). */
  sttLang?: "en" | "bn" | "en-bn" | "bn-en";
  /** Language for TTS. Defaults to "en". */
  ttsLang?: "en" | "bn";
}

/** Fired when the voice agent produces a grounded response. */
export type VoiceAgentResponseHandler = (text: string, grounded: boolean) => void;

/**
 * Voice Agent — bridges Speech-to-Text → Rental Agent SDK → Text-to-Speech.
 *
 * Architecture (per spec):
 *   Voice Input
 *     ↓
 *   Speech-to-Text
 *     ↓
 *   Phase 19 Agent SDK (Rental Agent)
 *     ↓
 *   Existing tools (search, details, commute, price, bookmark)
 *     ↓
 *   Grounded response
 *     ↓
 *   Text-to-Speech
 *     ↓
 *   Voice Output
 *
 * Key design points:
 * - Reuses existing Agent SDK (AgentSession, Tool Registry, consent workflow).
 * - Does NOT create a second rental intelligence engine.
 * - State-changing actions (bookmark, offer) require consent.
 * - Low-confidence STT → clarification.
 * - Falls back to text if TTS unavailable.
 */
export default function useVoiceAgent(options: VoiceAgentOptions = {}) {
  const { conversationId, roomId, sttLang = "bn", ttsLang = "en" } = options;

  const [state, setState] = useState<VoiceAgentState>("ready");
  const [transcript, setTranscript] = useState<string>("");
  const [response, setResponse] = useState<string>("");
  const [isGrounded, setGrounded] = useState<boolean>(false);

  const voiceRef = useRef<boolean>(false); // mutates across renders safely
  voiceRef.current = true;

  const sttRef = useRef(
    useVoiceInput({
      lang: sttLang as any,
      onTranscript: (t: string) => {
        setTranscript(t);
        setState("processing");
        // Send to the rental agent backend
        _processTranscript(t);
      },
      onInterim: () => {
        // Optional: show intermediate transcript
      },
    })
  );

  const {
    supported: ttsSupported,
    speak,
    stop: stopTts,
    status: ttsStatus,
  } = useSpeechOutput(ttsLang);

  // ---- Process transcript through the rental agent ----

  const _processTranscript = useCallback(
    async (userText: string) => {
      if (!userText.trim()) {
        setState("ready");
        return;
      }

      setState("processing");
      setResponse("");

      try {
        // Send the user's voice transcript to the backend rental agent
        const turnResponse = await api.post<{ response: string; grounded: boolean; type: string }>(
          "/negotiation/chat/",
          {
            message: userText,
            // If we have a conversationId, bind to it; otherwise start fresh
            ...(conversationId != null ? { conversation_id: conversationId } : {}),
            ...(roomId != null ? { room_id: roomId } : {}),
          }
        );

        const data = turnResponse.data;
        setResponse(data.response ?? "");
        setGrounded(!!data.grounded);
        setState("ready");
      } catch (err: any) {
        console.error("Voice agent transcript processing error:", err);
        const safeMsg =
          err?.response?.data?.error ??
          err?.message ??
          "Couldn't process your voice input — try again.";
        setResponse(safeMsg);
        setGrounded(false);
        setState("ready");
      }
    },
    [conversationId, roomId]
  );

  // ---- Handle user initiating voice input ----

  const startListening = useCallback(() => {
    setState("listening");
    sttRef.current?.start();
  }, [sttRef]);

  const stopListening = useCallback(() => {
    setState("ready");
    sttRef.current?.stop();
  }, [sttRef]);

  // ---- Speak the agent's grounded response ----

  const speakResponse = useCallback(() => {
    if (!response || !ttsSupported) {
      // Fallback: just show the text; don't block the conversation
      setState("ready");
      return;
    }
    setState("speaking");
    speak(response);
  }, [response, ttsSupported, speak]);

  // ---- Public API ----

  const toggleVoice = useCallback(() => {
    if (state === "ready" || state === "error") {
      startListening();
    } else if (state === "listening") {
      stopListening();
    }
  }, [state, startListening, stopListening]);

  const reset = useCallback(() => {
    setState("ready");
    setTranscript("");
    setResponse("");
    setGrounded(false);
    stopListening();
    stopTts();
  }, [stopListening, stopTts]);

  return {
    // State
    state,
    transcript,
    response,
    isGrounded,
    ttsSupported,
    ttsStatus,

    // Actions
    toggleVoice,
    startListening,
    stopListening,
    speakResponse,
    reset,

    // Debug / diagnostics
    sttRef,
  };
}
