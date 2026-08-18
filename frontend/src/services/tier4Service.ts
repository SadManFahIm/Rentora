import { api } from "./api";

// ============================================================
// TIER 4 SERVICE — AI Property Comparison, Rental Advisor,
// Negotiation Assistant, Agreement Checker, Landlord Copilot,
// Demand Forecast, Smart Alerts
// ============================================================

export interface CompareResult {
  rooms: {
    id: number;
    title: string;
    image: string | null;
    price: number;
    price_per_sqft: number | null;
    area: string;
    room_type: string;
    verified: boolean;
    size_sqft: number | null;
    amenities: string[];
    market_position: string | null;
    quality_score: number | null;
  }[];
  columns: Record<string, { label: string; values: Record<number, unknown> }>;
  summary: {
    count: number;
    cheapest?: { id: number; title: string; price: number };
    best_value?: { id: number; title: string; price_per_sqft: number };
    verified_count: number;
  };
}

export interface RentalAdvice {
  budget_max: number;
  room_type: string;
  affordability: { ratio: number | null; level: string; hint: string };
  recommendations: {
    area: string;
    label: string;
    median_rent: number | null;
    sample_size: number;
    available_in_budget: number;
    fits_budget: boolean;
  }[];
  checklist: string[];
}

export interface NegotiationDraft {
  listing_id: number;
  listing_price: number;
  suggested_offer: number;
  market_median: number | null;
  reason: string;
  draft_en: string;
  draft_bn: string;
}

export interface AgreementCheck {
  verdict: string;
  risk_level: string;
  clauses: { clause: string; risk: string; explanation: string }[];
  missing: string[];
  disclaimer: string;
}

export interface LandlordInsight {
  listing_id: number;
  title: string;
  price_compare: {
    listing_price: number;
    market_median: number | null;
    percentile_25?: number;
    percentile_75?: number;
    position?: string;
  };
  interest_30d: { bookings: number; wishlist_saves: number; reviews: number };
  quality: { score: number | null; level: string | null; suggestions: string[] } | null;
  suggestions: string[];
}

export interface DemandForecast {
  area: string;
  demand_index: number | null;
  direction: string;
  total_signals: number;
  weekly_series: number[];
  forecast_30d: number | null;
  note: string;
}

export interface SmartAlert {
  id: number;
  title: string;
  message: string;
  notification_type: string;
  is_read: boolean;
  created_at: string;
  priority: number;
  reason: string;
}

export const tier4Service = {
  /** GET /rooms/compare/?ids=1,2,3 → side-by-side comparison table. */
  async compare(ids: number[]): Promise<CompareResult> {
    const { data } = await api.get<CompareResult>("/rooms/compare/", {
      params: { ids: ids.join(",") },
    });
    return data;
  },

  /** POST /copilot/advisor/ → affordable-area recommendations. */
  async advisor(input: {
    budget_max: number;
    room_type?: string;
    area?: string;
    monthly_income?: number | null;
  }): Promise<RentalAdvice> {
    const { data } = await api.post<RentalAdvice>("/copilot/advisor/", input);
    return data;
  },

  /** POST /copilot/negotiate/ → grounded counter-offer draft (EN + BN). */
  async negotiate(input: {
    listing_id: number;
    target_price?: number | null;
    role?: "tenant" | "landlord";
    tone?: string;
  }): Promise<NegotiationDraft> {
    const { data } = await api.post<NegotiationDraft>("/copilot/negotiate/", input);
    return data;
  },

  /** POST /copilot/agreement-check/ → first-pass clause review. */
  async agreementCheck(text: string): Promise<AgreementCheck> {
    const { data } = await api.post<AgreementCheck>("/copilot/agreement-check/", {
      text,
    });
    return data;
  },

  /** POST /copilot/landlord/ → diagnose one of my listings. */
  async landlordInsight(listingId: number): Promise<LandlordInsight> {
    const { data } = await api.post<LandlordInsight>("/copilot/landlord/", {
      listing_id: listingId,
    });
    return data;
  },

  /** GET /analytics/forecast/?area= → demand index + 30-day trend. */
  async forecast(area?: string): Promise<DemandForecast> {
    const { data } = await api.get<DemandForecast>("/analytics/forecast/", {
      params: area ? { area } : undefined,
    });
    return data;
  },

  /** GET /notifications/smart/ → priority-ranked alerts. */
  async smartAlerts(): Promise<SmartAlert[]> {
    const { data } = await api.get<{ alerts: SmartAlert[] }>("/notifications/smart/");
    return data.alerts;
  },
};

export default tier4Service;
