import { useCallback, useEffect, useRef, useState } from "react";
import {
  approveNegotiationProposal,
  cancelNegotiation,
  getNegotiation,
  getNegotiationConversation,
  getNegotiationRun,
  listNegotiationConversations,
  listNegotiations,
  rejectNegotiation,
  rejectNegotiationOffer,
  rejectNegotiationProposal,
  sendNegotiationTurn,
  type NegotiationPayload,
  type NegotiationRow,
} from "../services/negotiationAgentService";
import {
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

export interface NegotiationAgentState {
  messages: RentalAgentMessage[];
  proposals: RentalAgentProposal[];
  suggestions: RentalAgentSuggestion[];
  conversationId: number | null;
  sending: boolean;
  acting: boolean;
  error: string;
  featureEnabled: boolean;
  agentName: string;
  agentDescription: string;
  lastAction: string;
  negotiations: NegotiationRow[];
  activeKey: string | null;
  negotiation: NegotiationPayload | null;
  negotiationLoading: boolean;
}

const EMPTY_STATE: NegotiationAgentState = {
  messages: [],
  proposals: [],
  suggestions: [],
  conversationId: null,
  sending: false,
  acting: false,
  error: "",
  featureEnabled: true,
  agentName: "Negotiation Agent",
  agentDescription: "",
  lastAction: "",
  negotiations: [],
  activeKey: null,
  negotiation: null,
  negotiationLoading: false,
};

export interface UseNegotiationAgentReturn extends NegotiationAgentState {
  send: (text: string) => Promise<void>;
  reply: (text: string) => Promise<void>;
  approve: (proposalKey: string) => Promise<void>;
  reject: (proposalKey: string) => Promise<void>;
  openRoom: (id: number) => Promise<Room>;
  reset: () => Promise<void>;
  select: (negotiationKey: string) => Promise<void>;
  withdrawOffer: (offerKey: string) => Promise<void>;
  rejectOffer: (offerKey: string) => Promise<void>;
  rejectWhole: () => Promise<void>;
  cancelWhole: () => Promise<void>;
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
 * Phase 19.4 AI Negotiation Agent client state.
 *
 * Combines the rental-agent async turn loop (POST /negotiation/chat/ →
 * poll the run → reload the enriched conversation) with the participant
 * negotiation surface: the callers' negotiation list, the full offers +
 * timeline payload for one negotiation, and the plain-user actions
 * (withdraw own offer, reject counterpart offer, reject/cancel the whole
 * negotiation). Consent on the agent's offer/boundary/send proposals is the
 * same self-grant flow as the rental agent.
 */
export default function useNegotiationAgent(roomId?: number): UseNegotiationAgentReturn {
  const [state, setState] = useState<NegotiationAgentState>(EMPTY_STATE);

  const mountedRef = useRef(true);
  const conversationIdRef = useRef<number | null>(null);
  // negotiationKey -> bound AgentConversation id (per side, one conversation)
  const boundRef = useRef<Map<string, number>>(new Map());
  const activeKeyRef = useRef<string | null>(null);
  const stateRef = useRef(state);
  stateRef.current = state;
  activeKeyRef.current = state.activeKey;

  const reloadNegotiationCb = useCallback(async () => {
    const key = activeKeyRef.current;
    if (!key) return;
    try {
      const payload = await getNegotiation(key);
      if (mountedRef.current) setState((prev) => ({ ...prev, negotiation: payload }));
    } catch {
      // keep the last known payload
    }
  }, []);

  const setPartial = useCallback((patch: Partial<NegotiationAgentState>) => {
    setState((prev) => ({ ...prev, ...patch }));
  }, []);

  // ---- transcript loading (replaces the whole chat payload) ----
  const loadConversation = useCallback(
    async (conversationId: number) => {
      const payload = await getNegotiationConversation(conversationId);
      if (!mountedRef.current) return;
      conversationIdRef.current = payload.id;
      if (payload.negotiation?.key) {
        boundRef.current.set(payload.negotiation.key, payload.id);
      }
      setPartial({
        messages: payload.messages,
        proposals: payload.proposals,
        suggestions: payload.suggestions,
        conversationId: payload.id,
        featureEnabled: payload.feature_enabled,
        agentName: payload.agent.name,
        agentDescription: payload.agent.description,
        error: "",
      });
    },
    [setPartial]
  );

  const clearTranscript = useCallback(() => {
    conversationIdRef.current = null;
    setPartial({
      messages: [],
      proposals: [],
      suggestions: [],
      conversationId: null,
      error: "",
      lastAction: "",
    });
  }, [setPartial]);

  // ---- negotiation row list ----
  const refreshNegotiations = useCallback(async (): Promise<NegotiationRow[]> => {
    try {
      const rows = await listNegotiations();
      if (mountedRef.current) {
        setState((prev) => {
          const stillActive = prev.activeKey != null && rows.some((r) => r.key === prev.activeKey);
          return { ...prev, negotiations: rows, activeKey: stillActive ? prev.activeKey : null };
        });
      }
      return rows;
    } catch {
      return stateRef.current.negotiations;
    }
  }, []);

  // Bound negotiation conversation? Negotiations have at most one
  // AgentConversation per side; returning users rejoin it instead of starting
  // a fresh (unbound) chat.
  const resolveBoundConversation = useCallback(
    async (negotiationKey: string): Promise<number | null> => {
      const cached = boundRef.current.get(negotiationKey);
      if (cached != null) return cached;
      try {
        const convos = await listNegotiationConversations();
        for (const convo of convos) {
          try {
            const detail = await getNegotiationConversation(convo.id);
            if (detail.negotiation?.key === negotiationKey) {
              boundRef.current.set(negotiationKey, convo.id);
              return convo.id;
            }
          } catch {
            // skip unreadable conversations
          }
        }
      } catch {
        // backend unreachable — first user turn will bind via room_id
      }
      return null;
    },
    []
  );

  // ---- select a negotiation: load detail + resume its conversation ----
  const select = useCallback(
    async (negotiationKey: string) => {
      if (!negotiationKey || stateRef.current.negotiationLoading) return;
      setPartial({ activeKey: negotiationKey, negotiationLoading: true, error: "" });
      try {
        const payload = await getNegotiation(negotiationKey);
        if (!mountedRef.current) return;
        setPartial({
          negotiation: payload,
          featureEnabled: payload.features.negotiation_agent_enabled,
        });

        const bound = await resolveBoundConversation(negotiationKey);
        if (bound != null) {
          await loadConversation(bound);
        } else {
          clearTranscript();
        }
      } catch (err) {
        setPartial({ error: extractErrorMessage(err), negotiation: null });
      } finally {
        setPartial({ negotiationLoading: false });
      }
    },
    [setPartial, resolveBoundConversation, loadConversation, clearTranscript]
  );

  // Mount: load the negotiation list, then auto-open the room's negotiation
  // (when roomId is given) or the most recent one.
  useEffect(() => {
    mountedRef.current = true;
    void (async () => {
      const rows = await refreshNegotiations();
      if (!mountedRef.current) return;
      const target = roomId != null ? rows.find((r) => r.room_id === roomId) : rows[0];
      if (target) {
        await select(target.key);
      } else if (roomId != null) {
        // No negotiation yet for this listing — welcome state; the first
        // user turn starts one via room_id.
        clearTranscript();
      }
    })();
    return () => {
      mountedRef.current = false;
    };
  }, [roomId, refreshNegotiations, select, clearTranscript]);

  // ---- poll a run until terminal, then pull the fresh transcript ----
  const waitForRun = useCallback(async (runKey: string): Promise<RentalAgentRun> => {
    let run: RentalAgentRun | null = null;
    for (let i = 0; i < MAX_POLLS && !isTerminalRun(run); i += 1) {
      if (!mountedRef.current) throw new Error("unmounted");
      await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
      try {
        run = await getNegotiationRun(runKey);
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
      if (!clean || stateRef.current.sending) return;

      const conversationId = conversationIdRef.current;
      const listingId = roomId ?? stateRef.current.negotiation?.room_id;
      setPartial({
        sending: true,
        error: "",
        lastAction: "Agent is thinking.",
        messages: [
          ...stateRef.current.messages,
          { id: -Date.now(), role: "user", content: clean, created_at: null, cards: [] },
        ],
      });

      try {
        const turnInfo = await sendNegotiationTurn(clean, {
          conversationId: conversationId ?? undefined,
          roomId: conversationId == null && listingId != null ? listingId : undefined,
        });
        const run = await waitForRun(turnInfo.run_key);

        if (run.status === "completed") {
          await loadConversation(turnInfo.conversation_id);
          if (activeKeyRef.current) {
            await reloadNegotiationCb();
            await refreshNegotiations();
          }
          setPartial({ sending: false });
        } else {
          const reason = run.error_message || run.termination_reason || run.status;
          setPartial({
            sending: false,
            error: reason ? `Agent couldn't finish: ${reason}` : "Agent couldn't finish that turn.",
            lastAction: "",
          });
        }
      } catch (err) {
        setPartial({
          sending: false,
          error: extractErrorMessage(err),
          lastAction: "",
        });
      }
    },
    [roomId, setPartial, waitForRun, loadConversation, reloadNegotiationCb, refreshNegotiations]
  );

  // ---- consent on agent proposals (self-grant, same as rental agent) ----
  const reloadAfterConsent = useCallback(async () => {
    const id = conversationIdRef.current;
    if (id != null) await loadConversation(id);
    await reloadNegotiationCb();
  }, [loadConversation, reloadNegotiationCb]);

  const approve = useCallback(
    async (proposalKey: string) => {
      if (stateRef.current.sending || stateRef.current.acting) return;
      setPartial({ sending: true, error: "" });
      try {
        await approveNegotiationProposal(proposalKey);
        await reloadAfterConsent();
        setPartial({ lastAction: `Processed proposal ${proposalKey.slice(0, 8)}.` });
      } catch (err) {
        setPartial({ error: extractErrorMessage(err) });
        throw err;
      } finally {
        setPartial({ sending: false });
      }
    },
    [setPartial, reloadAfterConsent]
  );

  const reject = useCallback(
    async (proposalKey: string) => {
      if (stateRef.current.sending || stateRef.current.acting) return;
      setPartial({ sending: true, error: "" });
      try {
        await rejectNegotiationProposal(proposalKey);
        await reloadAfterConsent();
        setPartial({ lastAction: `Processed proposal ${proposalKey.slice(0, 8)}.` });
      } catch (err) {
        setPartial({ error: extractErrorMessage(err) });
        throw err;
      } finally {
        setPartial({ sending: false });
      }
    },
    [setPartial, reloadAfterConsent]
  );

  // ---- plain-user offer/negotiation actions ----
  const runAction = useCallback(
    async (fn: (key: string) => Promise<unknown>) => {
      if (stateRef.current.sending || stateRef.current.acting) return;
      const key = activeKeyRef.current;
      if (!key) return;
      setPartial({ acting: true, error: "" });
      try {
        await fn(key);
        await reloadNegotiationCb();
        await refreshNegotiations();
      } catch (err) {
        setPartial({ error: extractErrorMessage(err) });
      } finally {
        setPartial({ acting: false });
      }
    },
    [setPartial, reloadNegotiationCb, refreshNegotiations]
  );

  const withdrawOffer = useCallback(
    (offerKey: string) => runAction((key) => rejectNegotiationOffer(key, offerKey, "")),
    [runAction]
  );

  const rejectOffer = useCallback(
    (offerKey: string) => runAction((key) => rejectNegotiationOffer(key, offerKey, "")),
    [runAction]
  );

  const rejectWhole = useCallback(
    () => runAction((key) => rejectNegotiation(key, "")),
    [runAction]
  );

  const cancelWhole = useCallback(
    () => runAction((key) => cancelNegotiation(key, "")),
    [runAction]
  );

  const openRoom = useCallback(async (id: number) => {
    const { default: roomService } = await import("../services/roomService");
    return roomService.getRoomById(id);
  }, []);

  // ---- fresh chat (same negotiation; a new turn re-binds via room_id) ----
  const reset = useCallback(async () => {
    conversationIdRef.current = null;
    if (!mountedRef.current) return;
    setState((prev) => ({ ...EMPTY_STATE, negotiations: prev.negotiations }));
  }, []);

  return {
    ...state,
    send: turn,
    reply: turn,
    approve,
    reject,
    openRoom,
    reset,
    select,
    withdrawOffer,
    rejectOffer,
    rejectWhole,
    cancelWhole,
  };
}
