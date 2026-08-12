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

export interface CopilotChatResponse {
  session_id: string;
  message: string;
  intent: CopilotIntent;
  listings: CopilotListing[];
  total_count: number;
  suggestions: string[];
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
 * keep follow-up context (area/budget persist across turns).
 */
export async function sendCopilotMessage(
  message: string,
  sessionId: string | null
): Promise<CopilotChatResponse> {
  const { data } = await api.post<CopilotChatResponse>("/copilot/chat/", {
    message,
    ...(sessionId ? { session_id: sessionId } : {}),
  });
  return data;
}
