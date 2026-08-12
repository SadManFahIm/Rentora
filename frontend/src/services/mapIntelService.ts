import { api } from "./api";
import type { Room } from "../types";

/** Per-area aggregate stats from the backend intelligence engine. */
export interface AreaIntel {
  area: string;
  lat: number | null;
  lng: number | null;
  listings: number;
  available: number;
  avg_rent: number | null;
  median_rent: number | null;
  min_rent: number | null;
  max_rent: number | null;
  avg_size_sqft: number | null;
  demand: {
    score: number;
    label: string;
    views_30d: number;
    saves_30d: number;
    bookings_30d: number;
    listings: number;
  };
  metro_access: number | null;
  price_trend_pct: number | null;
}

export interface CommuteResult {
  mode: "walking" | "driving" | "transit";
  minutes: number | null;
  distance_km: number;
  estimate: boolean;
  detail: string;
}

export interface ValueScore {
  score: number;
  factors: {
    price_fit: number;
    amenities: number;
    quality: number;
    verified: number;
    demand: number;
    metro: number;
  };
  price_vs_market_pct: number | null;
}

export interface AffordabilityRow {
  area: string;
  lat: number | null;
  lng: number | null;
  total: number;
  within_budget: number;
  percent: number;
}

export interface IdealArea {
  area: string;
  lat: number | null;
  lng: number | null;
  score: number;
  avg_rent: number | null;
  affordability_pct: number;
  commute_minutes: number | null;
  metro_access: number | null;
  listings: number;
  reasons: string[];
}

export interface MapSearchResult {
  query: string;
  intent: {
    budget_max: number | null;
    areas: string[];
    room_type: string | null;
    gender: string | null;
    months: string[];
    hints: string[];
    amenities: string[];
    metro_walk: boolean;
    raw: string;
  };
  count: number;
  rooms: Room[];
  target: { lat: number; lng: number; kind: string; name: string } | null;
}

export const mapIntelKeys = {
  all: ["map-intel"] as const,
  stats: (area?: string) => [...mapIntelKeys.all, "stats", area ?? "all"] as const,
  commute: (params: object) => [...mapIntelKeys.all, "commute", params] as const,
  value: (ids: number[]) => [...mapIntelKeys.all, "value", ids] as const,
  affordability: (budget: number) => [...mapIntelKeys.all, "affordability", budget] as const,
  ideal: (params: object) => [...mapIntelKeys.all, "ideal", params] as const,
  search: (q: string) => [...mapIntelKeys.all, "search", q] as const,
};

async function getStats(area?: string): Promise<AreaIntel[]> {
  return api.get("/rooms/map-intel/stats/", { params: area ? { area } : {} }).then((r) => r.data);
}

async function getCommute(params: {
  from_lat: number;
  from_lng: number;
  to_lat: number;
  to_lng: number;
  mode: "walking" | "driving" | "transit";
}): Promise<CommuteResult> {
  return api.get("/rooms/map-intel/commute/", { params }).then((r) => r.data);
}

async function getValue(ids: number[]): Promise<Record<string, ValueScore>> {
  if (ids.length === 0) return {};
  return api.get("/rooms/map-intel/value/", { params: { ids: ids.join(",") } }).then((r) => r.data);
}

async function getAffordability(budget: number): Promise<AffordabilityRow[]> {
  return api.get("/rooms/map-intel/affordability/", { params: { budget } }).then((r) => r.data);
}

async function getIdealAreas(params: {
  budget: number;
  work_lat?: number;
  work_lng?: number;
  max_commute?: number;
  room_type?: string;
}): Promise<IdealArea[]> {
  return api.get("/rooms/map-intel/ideal-areas/", { params }).then((r) => r.data);
}

async function mapSearch(q: string): Promise<MapSearchResult> {
  return api.get("/rooms/map-intel/search/", { params: { q } }).then((r) => r.data);
}

export const mapIntelService = {
  getStats,
  getCommute,
  getValue,
  getAffordability,
  getIdealAreas,
  mapSearch,
};
