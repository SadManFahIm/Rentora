import api from "./api";

/** What the backend understood from a Copilot message (UI chips). */
export interface CopilotIntent {
  budget_max: number | null;
  areas: string[];
  room_type: string | null;
  gender: string | null;
  months: string[];
  amenities: string[];
  property_words: string[];
  hints: string[];
}

/** One retrieved listing — always backed by a real DB row (never invented). */
export interface CopilotListing {
  id: number;
  title: string;
  price: number;
  area: string;
  room_type: string;
  amenities: string[];
  verified: boolean;
  tier: string;
  image: string | null;
}

/** Grounded fact card for one listing (Tier 3 RAG source document). */
export interface CopilotListingFacts {
  id: number;
  title: string;
  price: number;
  area: string;
  area_display: string;
  room_type: string;
  room_type_display: string;
  gender_preference: string;
  size_sqft: number | null;
  amenities: string[];
  verified: boolean;
  available: boolean;
  address: string;
  description: string;
  metro_km: number | null;
  image: string | null;
}

export interface CopilotChatResponse {
  session_id: string;
  message: string;
  intent: CopilotIntent;
  listings: CopilotListing[];
  total_count: number;
  suggestions: string[];
  mode: "search" | "listing";
  listing: CopilotListingFacts | null;
  aspect: string | null;
}

export interface CopilotChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  listings?: CopilotListing[];
  suggestions?: string[];
  intent?: CopilotIntent;
}

/**
 * POST /copilot/chat/ — one conversational turn. Echo back `sessionId` to
 * keep follow-up context (area/budget persist across turns). Pass
 * `listingId` to ground the turn on a single listing (RAG over one doc).
 */
export async function sendCopilotMessage(
  message: string,
  sessionId: string | null,
  listingId?: number | null
): Promise<CopilotChatResponse> {
  const { data } = await api.post<CopilotChatResponse>("/copilot/chat/", {
    message,
    ...(sessionId ? { session_id: sessionId } : {}),
    ...(listingId ? { listing_id: listingId } : {}),
  });
  return data;
}

/** GET /copilot/listing/<id>/ — the grounded fact card for a listing. */
export async function getListingFacts(listingId: number): Promise<CopilotListingFacts> {
  const { data } = await api.get<CopilotListingFacts>(`/copilot/listing/${listingId}/`);
  return data;
}
