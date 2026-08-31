import { useCallback, useEffect, useRef, useState } from "react";
import {
  approveRentalAgentProposal,
  getRentalAgentConversation,
  getRentalAgentRun,
  listRentalAgentConversations,
  rejectRentalAgentProposal,
  sendRentalAgentTurn,
  type RentalAgentMessage,
  type RentalAgentProposal,
  type RentalAgentRun,
  type RentalAgentSuggestion,
} from "../services/rentalAgentService";
import type { Room } from "../types";

const POLL_INTERVAL_MS = 1500;
const MAX_POLLS = 40;

const TERMINAL = new Set(["completed", "terminated", "failed", "cancelled"]);

function isTerminalRun(run: RentalAgentRun | null): boolean {
  return !!run && TERMINAL.has(run.status);
}

export interface RentalAgentState {
  messages: RentalAgentMessage[];
  proposals: RentalAgentProposal[];
  suggestions: RentalAgentSuggestion[];
  conversationId: number | null;
  sending: boolean;
  error: string;
  featureEnabled: boolean;
  agentName: string;
  agentDescription: string;
  lastAction: string;
}

const EMPTY_STATE: RentalAgentState = {
  messages: [],
  proposals: [],
  suggestions: [],
  conversationId: null,
  sending: false,
  error: "",
  featureEnabled: true,
  agentName: "Rentora Agent",
  agentDescription: "",
  lastAction: "",
};

interface UseRentalAgentReturn extends RentalAgentState {
  send: (text: string) => Promise<void>;
  reply: (text: string) => Promise<void>;
  approve: (proposalKey: string) => Promise<void>;
  reject: (proposalKey: string) => Promise<void>;
  openRoom: (id: number) => Promise<Room>;
  reset: () => Promise<void>;
}

function extractErrorMessage(err: unknown): string {
  if (typeof err === "object" && err !== null) {
    const anyErr = err as {
      response?: { data?: { error?: unknown; message?: unknown } };
      message?: unknown;
    };
    const raw = anyErr.response?.data?.error ?? anyErr.response?.data?.message ?? anyErr.message;
    if (typeof raw === "string" && raw.trim()) return raw.trim();
  }
  return "Couldn't reach the agent right now - try again.";
}

/**
 * Phase 19.2 AI Rental Agent client state.
 *
 * A turn is async: POST /rental/chat/ returns the conversation + a run key,
 * we poll the run until it reaches a terminal state (Celery task), then
 * reload the enriched conversation payload so every rendered card/proposal/
 * chip is the backend's grounded snapshot.
 */
export default function useRentalAgent(): UseRentalAgentReturn {
  const [state, setState] = useState<RentalAgentState>(EMPTY_STATE);
  const conversationIdRef = useRef<number | null>(null);
  const mountedRef = useRef(true);

  // ---- payload loading (same shape the chat API returns) ----
  const loadConversation = useCallback(async (conversationId: number) => {
    const payload = await getRentalAgentConversation(conversationId);
    if (!mountedRef.current) return;
    conversationIdRef.current = payload.id;
    setState((prev) => ({
      ...prev,
      messages: payload.messages,
      proposals: payload.proposals,
      suggestions: payload.suggestions,
      conversationId: payload.id,
      featureEnabled: payload.feature_enabled,
      agentName: payload.agent.name,
      agentDescription: payload.agent.description,
      error: "",
      lastAction: "",
    }));
  }, []);

  // Mount-resume: returning tenants land on their latest agent conversation
  // (kept welcome-state when there is none).
  useEffect(() => {
    mountedRef.current = true;
    void (async () => {
      try {
        const convos = await listRentalAgentConversations();
        if (mountedRef.current && convos[0]) {
          await loadConversation(convos[0].id);
        }
      } catch {
        // no conversations or unreachable backend — keep the welcome state
      }
    })();
    return () => {
      mountedRef.current = false;
    };
  }, [loadConversation]);

  // ---- poll a run until terminal, then pull the fresh transcript ----
  const waitForRun = useCallback(async (runKey: string): Promise<RentalAgentRun> => {
    let run: RentalAgentRun | null = null;
    for (let i = 0; i < MAX_POLLS && !isTerminalRun(run); i += 1) {
      if (!mountedRef.current) throw new Error("unmounted");
      await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
      try {
        run = await getRentalAgentRun(runKey);
      } catch {
        // transient poll failure - keep waiting; the task may still finish
      }
    }
    if (!run) {
      throw new Error("The agent is taking a while - check back shortly.");
    }
    return run;
  }, []);

  // ---- send a turn ----
  const turn = useCallback(
    async (text: string) => {
      const clean = text.trim();
      if (!clean || state.sending) return;

      const conversationId = conversationIdRef.current;
      setState((prev) => ({
        ...prev,
        sending: true,
        error: "",
        lastAction: "Agent is thinking.",
        messages: [
          ...prev.messages,
          { id: -Date.now(), role: "user", content: clean, created_at: null, cards: [] },
        ],
      }));

      try {
        const turnInfo = await sendRentalAgentTurn(clean, conversationId ?? undefined);
        const run = await waitForRun(turnInfo.run_key);

        if (run.status === "completed") {
          await loadConversation(turnInfo.conversation_id);
        } else {
          const reason = run.error_message || run.termination_reason || run.status;
          setState((prev) => ({
            ...prev,
            sending: false,
            error: reason ? `Agent couldn't finish: ${reason}` : "Agent couldn't finish that turn.",
            lastAction: "",
          }));
        }
      } catch (err) {
        setState((prev) => ({
          ...prev,
          sending: false,
          error: extractErrorMessage(err),
          lastAction: "",
        }));
      }
    },
    [state.sending, loadConversation, waitForRun]
  );

  // ---- consent actions ----
  const reloadAfterConsent = useCallback(
    async (proposalKey: string) => {
      const id = conversationIdRef.current;
      if (id == null) return;
      await loadConversation(id);
      setState((prev) => ({
        ...prev,
        lastAction: `Processed proposal ${proposalKey.slice(0, 8)}.`,
      }));
    },
    [loadConversation]
  );

  const approve = useCallback(
    async (proposalKey: string) => {
      if (state.sending) return;
      setState((prev) => ({ ...prev, sending: true, error: "" }));
      try {
        await approveRentalAgentProposal(proposalKey);
        await reloadAfterConsent(proposalKey);
      } catch (err) {
        const message = extractErrorMessage(err);
        setState((prev) => ({ ...prev, error: message }));
        throw err;
      } finally {
        setState((prev) => ({ ...prev, sending: false }));
      }
    },
    [state.sending, reloadAfterConsent]
  );

  const reject = useCallback(
    async (proposalKey: string) => {
      if (state.sending) return;
      setState((prev) => ({ ...prev, sending: true, error: "" }));
      try {
        await rejectRentalAgentProposal(proposalKey);
        await reloadAfterConsent(proposalKey);
      } catch (err) {
        const message = extractErrorMessage(err);
        setState((prev) => ({ ...prev, error: message }));
        throw err;
      } finally {
        setState((prev) => ({ ...prev, sending: false }));
      }
    },
    [state.sending, reloadAfterConsent]
  );

  const openRoom = useCallback(async (id: number) => {
    const { default: roomService } = await import("../services/roomService");
    return roomService.getRoomById(id);
  }, []);

  // ---- fresh conversation ----
  const reset = useCallback(async () => {
    conversationIdRef.current = null;
    if (!mountedRef.current) return;
    setState(EMPTY_STATE);
  }, []);

  return { ...state, send: turn, reply: turn, approve, reject, openRoom, reset };
}
