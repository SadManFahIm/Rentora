import { api } from "./api";

/**
 * Tier-5 API client — price recommendation + AI listing draft.
 *
 * Both endpoints are deterministic and grounded server-side (no LLM):
 * - price recommendation combines area demand, market position and the
 *   listing's own interest signals into a raise/hold/lower suggestion.
 * - the description draft is built from the landlord's own fields.
 */

export interface PriceRecommendation {
  room_id: number;
  current_price: number;
  suggested_price: number;
  direction: "raise" | "hold" | "lower";
  confidence: "high" | "medium" | "low";
  reasons: string[];
  signals: {
    area_demand_index: number | null;
    area_demand_direction: string | null;
    market_position: string | null;
    interest_30d: { bookings_30d: number; wishlist_30d: number; total: number };
  };
  note: string;
  // Phase 15 — C7 dynamic pricing v2 (always present; nullable values when
  // nothing is grounded — the API never invents a figure).
  version?: 2;
  dynamic_price?: number | null;
  demand_momentum_pct?: number | null;
  window?: { min: number; max: number } | null;
  valid_until?: string | null;
  drivers?: { factor: string; effect: "raise" | "hold" | "lower"; detail: string }[];
}

export interface ListingDraftRequest {
  title?: string;
  room_type?: string;
  price?: number;
  area?: string;
  size_sqft?: number;
  gender_preference?: string;
  amenities?: string[];
}

export interface ListingDraft {
  title: string;
  description: string;
  amenities: string[];
  note: string;
}

export const tier5Service = {
  /** GET /rooms/:id/price-recommendation/ — owner/admin only. */
  async priceRecommendation(roomId: number): Promise<PriceRecommendation> {
    const { data } = await api.get<PriceRecommendation>(`/rooms/${roomId}/price-recommendation/`);
    return data;
  },

  /** POST /rooms/generate-description/ — draft a listing (authenticated). */
  async generateDescription(payload: ListingDraftRequest): Promise<ListingDraft> {
    const { data } = await api.post<ListingDraft>("/rooms/generate-description/", payload);
    return data;
  },
};

export default tier5Service;
