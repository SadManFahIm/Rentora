import { describe, expect, it, vi, beforeEach } from "vitest";

vi.mock("./api", () => ({
  api: {
    get: vi.fn(),
  },
}));

import { api } from "./api";
import {
  mapIntelService,
  mapIntelKeys,
  type AreaIntel,
  type IdealArea,
  type MapSearchResult,
} from "./mapIntelService";

const areaRow: AreaIntel = {
  area: "Uttara",
  lat: 23.8759,
  lng: 90.3795,
  listings: 248,
  available: 210,
  avg_rent: 11200,
  median_rent: 10500,
  min_rent: 6000,
  max_rent: 25000,
  avg_size_sqft: 850,
  demand: {
    score: 80,
    label: "Very High",
    views_30d: 1200,
    saves_30d: 96,
    bookings_30d: 14,
    listings: 248,
  },
  metro_access: 95,
  price_trend_pct: 8.2,
};

describe("mapIntelService", () => {
  beforeEach(() => vi.clearAllMocks());

  it("fetches area statistics (optionally for one area)", async () => {
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: [areaRow] });
    const res = await mapIntelService.getStats();
    expect(res).toHaveLength(1);
    expect(res[0].area).toBe("Uttara");
    expect(res[0].demand.label).toBe("Very High");
    expect(api.get).toHaveBeenCalledWith("/rooms/map-intel/stats/", { params: {} });

    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: [areaRow] });
    await mapIntelService.getStats("Uttara");
    expect(api.get).toHaveBeenLastCalledWith("/rooms/map-intel/stats/", {
      params: { area: "Uttara" },
    });
  });

  it("requests a commute ETA with the chosen mode", async () => {
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: {
        mode: "walking",
        minutes: 22,
        distance_km: 1.76,
        estimate: true,
        detail: "Walking estimate",
      },
    });
    const res = await mapIntelService.getCommute({
      from_lat: 23.8759,
      from_lng: 90.3795,
      to_lat: 23.7928,
      to_lng: 90.4067,
      mode: "walking",
    });
    expect(res.mode).toBe("walking");
    expect(res.minutes).toBe(22);
    expect(api.get).toHaveBeenCalledWith("/rooms/map-intel/commute/", {
      params: {
        from_lat: 23.8759,
        from_lng: 90.3795,
        to_lat: 23.7928,
        to_lng: 90.4067,
        mode: "walking",
      },
    });
  });

  it("returns an empty map for value scores when no ids are given", async () => {
    const res = await mapIntelService.getValue([]);
    expect(res).toEqual({});
    expect(api.get).not.toHaveBeenCalled();
  });

  it("batches value-score ids as a comma list", async () => {
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: {
        1: {
          score: 91,
          factors: {
            price_fit: 100,
            amenities: 28,
            quality: 47,
            verified: 100,
            demand: 80,
            metro: 95,
          },
          price_vs_market_pct: -5.0,
        },
      },
    });
    await mapIntelService.getValue([1, 2, 3]);
    expect(api.get).toHaveBeenCalledWith("/rooms/map-intel/value/", {
      params: { ids: "1,2,3" },
    });
  });

  it("fetches affordability shares for a budget", async () => {
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: [
        { area: "Mirpur", lat: 23.8, lng: 90.35, total: 421, within_budget: 400, percent: 95 },
      ],
    });
    const res = await mapIntelService.getAffordability(10000);
    expect(res[0].percent).toBe(95);
    expect(api.get).toHaveBeenCalledWith("/rooms/map-intel/affordability/", {
      params: { budget: 10000 },
    });
  });

  it("ranks ideal areas from a budget + destination profile", async () => {
    const ideal: IdealArea = {
      area: "Mirpur",
      lat: 23.8069,
      lng: 90.3687,
      score: 88,
      avg_rent: 9000,
      affordability_pct: 100,
      commute_minutes: 28,
      metro_access: 82,
      listings: 421,
      reasons: ["100% of Mirpur listings fit your ৳10,000 budget"],
    };
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: [ideal] });
    const res = await mapIntelService.getIdealAreas({
      budget: 10000,
      work_lat: 23.79,
      work_lng: 90.4,
      max_commute: 30,
    });
    expect(res[0].area).toBe("Mirpur");
    expect(res[0].reasons[0]).toContain("fit your");
    expect(api.get).toHaveBeenCalledWith("/rooms/map-intel/ideal-areas/", {
      params: { budget: 10000, work_lat: 23.79, work_lng: 90.4, max_commute: 30 },
    });
  });

  it("runs a natural-language map search", async () => {
    const search: MapSearchResult = {
      query: "Uttara 10k er moddhe furnished room",
      intent: {
        budget_max: 10000,
        areas: ["Uttara"],
        room_type: null,
        gender: null,
        months: [],
        hints: [],
        amenities: ["Furnished"],
        metro_walk: false,
        raw: "Uttara 10k er moddhe furnished room",
      },
      count: 1,
      rooms: [{ id: 1, name: "Room A", price: 8500, area: "Uttara" } as never],
      target: { lat: 23.8759, lng: 90.3795, kind: "area", name: "Uttara" },
    };
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: search });
    const res = await mapIntelService.mapSearch("Uttara 10k er moddhe furnished room");
    expect(res.count).toBe(1);
    expect(res.intent.areas).toEqual(["Uttara"]);
    expect(res.target?.kind).toBe("area");
    expect(api.get).toHaveBeenCalledWith("/rooms/map-intel/search/", {
      params: { q: "Uttara 10k er moddhe furnished room" },
    });
  });

  it("builds stable query keys for cache identity", () => {
    expect(mapIntelKeys.stats()).toEqual(["map-intel", "stats", "all"]);
    expect(mapIntelKeys.stats("Mirpur")).toEqual(["map-intel", "stats", "Mirpur"]);
    expect(mapIntelKeys.affordability(12000)).toEqual(["map-intel", "affordability", 12000]);
    expect(mapIntelKeys.search("mirpur")).toEqual(["map-intel", "search", "mirpur"]);
  });
});
