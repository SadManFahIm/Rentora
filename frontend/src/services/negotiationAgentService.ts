import { api } from "./api";
import type {
  RentalAgentCard,
  RentalAgentConversation,
  RentalAgentMessage,
  RentalAgentProposal,
  RentalAgentRun,
  RentalAgentSuggestion,
  RentalAgentTurnResponse,
} from "./rentalAgentService";

// ============================================================
// AI NEGOTIATION AGENT (Phase 19.4) — agent-assisted rent talks
// ============================================================

export type NegotiationRole = "tenant" | "landlord" | "";

export interface NegotiationOffer {
  key: string;
  kind: "offer" | "counter";
  amount: number;
  message: string;
  meta: Record<string, unknown>;
  status: string;
  sender_role: NegotiationRole;
  sender_name: string;
  created_at: string | null;
  expires_at: string | null;
  can_accept: boolean;
  can_reject: boolean;
  can_withdraw: boolean;
}

export interface NegotiationEvent {
  event: string;
  actor_name: string;
  detail: Record<string, unknown>;
  created_at: string | null;
}

/** Full participant payload for one negotiation (offers + timeline). */
export interface NegotiationPayload {
  key: string;
  room_id: number;
  room: RentalAgentCard;
  insights: {
    insights: string[];
    source: string;
  } | null;
  status: string;
  status_label: string;
  my_role: NegotiationRole;
  tenant: { name: string };
  landlord: { name: string; is_owner: boolean };
  peer_name: string;
  my_constraints: Record<string, number | null> | null;
  peer_constraints_set: boolean;
  offers: NegotiationOffer[];
  timeline: NegotiationEvent[];
  expires_at: string | null;
  is_open: boolean;
  features: { negotiation_agent_enabled: boolean };
  chat_room_id: number | null;
  can_reject: boolean;
  can_cancel: boolean;
}

/** Enriched conversation + the negotiation it is bound to (if any). */
export interface NegotiationConversation extends RentalAgentConversation {
  negotiation: NegotiationPayload | null;
}

export interface NegotiationRow {
  key: string;
  room_id: number;
  room_title: string;
  room_price: number;
  status: string;
  my_role: NegotiationRole;
  peer_name: string;
  updated_at: string;
  last_offer: {
    amount: number;
    status: string;
    kind: string;
    created_at: string | null;
  } | null;
}

export interface NegotiationConsentResult {
  proposal_key: string;
  status: string;
}

export interface NegotiationActionResult {
  ok: string;
  offer_key?: string;
  status: string;
}

export interface SendNegotiationTurnOptions {
  conversationId?: number;
  roomId?: number;
}

/** Send a turn: starts a new (optionally room-bound) negotiation chat or
 * continues an existing one. */
export const sendNegotiationTurn = (
  message: string,
  options: SendNegotiationTurnOptions = {}
): Promise<RentalAgentTurnResponse> =>
  api
    .post<RentalAgentTurnResponse>("/negotiation/chat/", {
      message,
      ...(options.conversationId != null ? { conversation_id: options.conversationId } : {}),
      ...(options.roomId != null ? { room_id: options.roomId } : {}),
    })
    .then((r) => r.data);

/** Poll one of the caller's negotiation-agent runs. */
export const getNegotiationRun = (
  runKey: string
): Promise<RentalAgentRun & { total_tokens?: number; estimated_cost_usd?: number }> =>
  api
    .get<RentalAgentRun & { total_tokens?: number; estimated_cost_usd?: number }>(
      `/negotiation/runs/${runKey}/`
    )
    .then((r) => r.data);

/** Fetch the enriched negotiation conversation (+ bound negotiation). */
export const getNegotiationConversation = (
  conversationId: number
): Promise<NegotiationConversation> =>
  api
    .get<NegotiationConversation>(`/negotiation/conversations/${conversationId}/`)
    .then((r) => r.data);

/** Only pending/applied proposals worth showing are returned by the payload. */
export const approveNegotiationProposal = (
  proposalKey: string,
  note?: string
): Promise<NegotiationConsentResult> =>
  api
    .post<NegotiationConsentResult>(`/negotiation/proposals/${proposalKey}/approve/`, {
      note: note ?? "",
    })
    .then((r) => r.data);

export const rejectNegotiationProposal = (
  proposalKey: string,
  note?: string
): Promise<NegotiationConsentResult> =>
  api
    .post<NegotiationConsentResult>(`/negotiation/proposals/${proposalKey}/reject/`, {
      note: note ?? "",
    })
    .then((r) => r.data);

/** The caller's negotiation-agent conversations (recent activity first). */
export const listNegotiationConversations = (): Promise<RentalAgentConversation[]> =>
  api.get<RentalAgentConversation[]>("/negotiation/conversations/").then((r) => r.data);

/** The caller's negotiations as participant (light rows, latest first). */
export const listNegotiations = (): Promise<NegotiationRow[]> =>
  api.get<NegotiationRow[]>("/negotiation/negotiations/").then((r) => r.data);

/** Full participant payload for one negotiation. */
export const getNegotiation = (negotiationKey: string): Promise<NegotiationPayload> =>
  api.get<NegotiationPayload>(`/negotiation/negotiations/${negotiationKey}/`).then((r) => r.data);

/** Counterparty rejects an outstanding offer; the sender withdraws it. */
export const rejectNegotiationOffer = (
  negotiationKey: string,
  offerKey: string,
  note?: string
): Promise<NegotiationActionResult> =>
  api
    .post<NegotiationActionResult>(
      `/negotiation/negotiations/${negotiationKey}/offers/${offerKey}/reject/`,
      { note: note ?? "" }
    )
    .then((r) => r.data);

/** Reject the whole negotiation (terminal). */
export const rejectNegotiation = (
  negotiationKey: string,
  note?: string
): Promise<NegotiationActionResult> =>
  api
    .post<NegotiationActionResult>(`/negotiation/negotiations/${negotiationKey}/reject/`, {
      note: note ?? "",
    })
    .then((r) => r.data);

/** Cancel the whole negotiation (terminal). */
export const cancelNegotiation = (
  negotiationKey: string,
  note?: string
): Promise<NegotiationActionResult> =>
  api
    .post<NegotiationActionResult>(`/negotiation/negotiations/${negotiationKey}/cancel/`, {
      note: note ?? "",
    })
    .then((r) => r.data);

export type {
  RentalAgentCard,
  RentalAgentConversation,
  RentalAgentMessage,
  RentalAgentProposal,
  RentalAgentRun,
  RentalAgentSuggestion,
  RentalAgentTurnResponse,
};
