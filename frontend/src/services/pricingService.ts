import api from "./api";

/** AI pricing suggestion v2 for an existing listing (owner/admin only). */
export interface PricingSuggestion {
  room_id: number;
  title: string;
  current_price: number;
  min_price: number | null;
  recommended_price: number | null;
  max_price: number | null;
  confidence: number;
  model_confidence: "high" | "low" | "none";
  demand_score: number;
  demand_label: "Low" | "Moderate" | "High" | "Very High";
  time_to_rent: {
    available: boolean;
    days_min?: number;
    days_max?: number;
    sample_count?: number;
    detail?: string;
  };
  reasons: string[];
  signals: {
    room_views_30d: number;
    area_avg_views_30d: number;
    platform_avg_views_30d: number;
    wishlist_count: number;
    booking_requests: number;
  };
  market_avg_price: number | null;
}

/** GET /pricing/suggestion/:id/ — owner or admin only. */
export async function getPricingSuggestion(roomId: number): Promise<PricingSuggestion> {
  const { data } = await api.get<PricingSuggestion>(`/pricing/suggestion/${roomId}/`);
  return data;
}
