import { api } from "./api";

// ============================================================
// MARKET REPORT SERVICE — the weekly rental market digest (C6)
// ============================================================

/** One area row of the weekly market digest. */
export interface MarketAreaRow {
  area: string;
  avg_price: number | null;
  median_price: number | null;
  sample_size: number;
  available_count: number;
  total_count: number;
  availability_pct: number;
  demand_index: number | null;
  direction: string | null;
  forecast_30d: number | null;
  prev_avg_price: number | null;
  price_change_pct: number | null;
}

export interface MarketHighlight {
  area: string;
  kind: "rising" | "falling";
  text: string;
}

/** GET /analytics/market-report/ — public, read-only digest. */
export interface MarketReport {
  week_label: string;
  as_of: string;
  areas: MarketAreaRow[];
  rising: string[];
  falling: string[];
  highlights: MarketHighlight[];
  summary_bn: string;
  baseline: boolean;
  note: string;
}

export const marketReportService = {
  async get(): Promise<MarketReport> {
    const { data } = await api.get<MarketReport>("/analytics/market-report/");
    return data;
  },

  /** POST /analytics/market-report/generate/ — admin-only: writes this
   * week's price snapshot and emails opted-in landlords. */
  async generate(): Promise<{ week_label: string; areas: number; baseline: boolean }> {
    const { data } = await api.post<{
      ok: boolean;
      week_label: string;
      areas: number;
      baseline: boolean;
      subscribed_emails: number;
    }>("/analytics/market-report/generate/");
    return {
      week_label: data.week_label,
      areas: data.areas,
      baseline: data.baseline,
    };
  },
};

export default marketReportService;
