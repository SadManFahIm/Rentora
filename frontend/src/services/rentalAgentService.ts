import { api } from "./api";

// ============================================================
// AI RENTAL AGENT (Phase 19.2) — tenant chat with the agent
// ============================================================

/** A grounded room card attached to an assistant message (never invented —
 * every field is read from a real stored Room). */
export interface RentalAgentCard {
  id: number;
  title: string;
  price_bdt: number | null;
  price_text: string;
  currency: string;
  area: string;
  area_display: string;
  room_type: string;
  room_type_display: string;
  gender_preference: string;
  size_sqft: number | null;
  amenities: string[];
  address: string;
  verified: boolean;
  featured: boolean;
  available: boolean;
  lat: number | null;
  lng: number | null;
  image: string | null;
  url: string;
}

export interface RentalAgentMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  created_at: string | null;
  cards: RentalAgentCard[];
}

export interface RentalAgentRun {
  key: string;
  status: "pending" | "running" | "completed" | "terminated" | "failed" | "cancelled";
  termination_reason: string;
  error_message: string;
  turn_count: number;
  tool_call_count: number;
  created_at: string | null;
  completed_at: string | null;
}

export interface RentalAgentProposal {
  key: string;
  tool: string;
  status: "pending" | "approved" | "rejected" | "expired" | "applied" | "failed";
  approval_required: string;
  room: RentalAgentCard | null;
  summary: string;
  created_at: string | null;
  expires_at: string | null;
  reviewed_at: string | null;
  conversation_id: number | null;
}

export interface RentalAgentSuggestion {
  label: string;
  text: string;
}

/** Full enriched conversation payload (transcript + proposals + chips). */
export interface RentalAgentConversation {
  id: number;
  title: string;
  status: string;
  feature_enabled: boolean;
  agent: { key: string; name: string; description: string };
  latest_run: RentalAgentRun | null;
  messages: RentalAgentMessage[];
  proposals: RentalAgentProposal[];
  suggestions: RentalAgentSuggestion[];
}

export interface RentalAgentTurnResponse {
  conversation_id: number;
  run_key: string;
  status: string;
  task_id: string;
}

export interface RentalAgentConsentResult {
  proposal_key: string;
  status: string;
}

/** Row shape returned by the conversations list endpoint (.values()). */
export interface RentalAgentConversationSummary {
  id: number;
  title: string;
  status: string;
  last_activity_at: string | null;
}

/** Send a turn: starts a new conversation (or continues one via id). */
export const sendRentalAgentTurn = (
  message: string,
  conversationId?: number
): Promise<RentalAgentTurnResponse> =>
  api
    .post<RentalAgentTurnResponse>("/rental/chat/", {
      message,
      ...(conversationId != null ? { conversation_id: conversationId } : {}),
    })
    .then((r) => r.data);

/** Poll one of the caller's rental-agent runs. */
export const getRentalAgentRun = (runKey: string): Promise<RentalAgentRun> =>
  api.get<RentalAgentRun>(`/rental/runs/${runKey}/`).then((r) => r.data);

/** Fetch the enriched conversation (messages, cards, proposals, chips). */
export const getRentalAgentConversation = (
  conversationId: number
): Promise<RentalAgentConversation> =>
  api.get<RentalAgentConversation>(`/rental/conversations/${conversationId}/`).then((r) => r.data);

/** Only pending/applied proposals worth showing are returned by the payload. */
export const approveRentalAgentProposal = (
  proposalKey: string,
  note?: string
): Promise<RentalAgentConsentResult> =>
  api
    .post<RentalAgentConsentResult>(`/rental/proposals/${proposalKey}/approve/`, {
      note: note ?? "",
    })
    .then((r) => r.data);

export const rejectRentalAgentProposal = (
  proposalKey: string,
  note?: string
): Promise<RentalAgentConsentResult> =>
  api
    .post<RentalAgentConsentResult>(`/rental/proposals/${proposalKey}/reject/`, {
      note: note ?? "",
    })
    .then((r) => r.data);

/** Fetch the caller's rental-agent conversations (recent activity first). */
export const listRentalAgentConversations = (): Promise<RentalAgentConversationSummary[]> =>
  api.get<RentalAgentConversationSummary[]>("/rental/conversations/").then((r) => r.data);
