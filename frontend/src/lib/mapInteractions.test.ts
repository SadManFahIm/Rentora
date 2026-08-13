import { describe, expect, it } from "vitest";
import {
  areaStats,
  formatRent,
  heatmapPopupHtml,
  isochronePopupHtml,
  isochroneStats,
  landmarkPopupHtml,
  metroRoutePopupHtml,
  nearbyStats,
  THEME_PAINTS,
  themePaintValue,
  TRAVEL_BAND_DARK_OPACITY,
  TRAVEL_BAND_LIGHT_OPACITY,
} from "./mapInteractions";
import type { Room } from "../types";

function room(overrides: Partial<Room>): Room {
  return {
    id: 1,
    name: "Test Room",
    type: "Single",
    gender: "Any",
    available: true,
    price: 10000,
    area: "Dhanmondi",
    address: "Road 27",
    lat: 23.75,
    lng: 90.37,
    verified: false,
    ...overrides,
  } as Room;
}

const ROOMS: Room[] = [
  room({ id: 1, price: 8000, area: "Dhanmondi", lat: 23.7501, lng: 90.3701 }),
  // ~1 km from room 1 — outside a 0.5 km radius but inside a 2 km radius.
  room({ id: 2, price: 12000, area: "Dhanmondi", lat: 23.759, lng: 90.37 }),
  room({ id: 3, price: 20000, area: "Gulshan", lat: 23.79, lng: 90.41 }),
];

describe("nearbyStats", () => {
  it("counts rooms within radius and computes avg/min/max", () => {
    const s = nearbyStats(ROOMS, 23.75, 90.37, 2);
    expect(s.count).toBe(2);
    expect(s.avgRent).toBe(10000);
    expect(s.minRent).toBe(8000);
    expect(s.maxRent).toBe(12000);
  });

  it("excludes rooms beyond the radius", () => {
    const s = nearbyStats(ROOMS, 23.75, 90.37, 0.5);
    expect(s.count).toBe(1); // only room 1
    expect(s.avgRent).toBe(8000);
  });
});

describe("areaStats", () => {
  it("is case-insensitive on area name", () => {
    const s = areaStats(ROOMS, "dhanmondi");
    expect(s.count).toBe(2);
    expect(s.avgRent).toBe(10000);
  });

  it("returns empty stats for unknown area", () => {
    const s = areaStats(ROOMS, "Mohammadpur");
    expect(s.count).toBe(0);
  });
});

describe("isochroneStats", () => {
  it("reuses the nearby model with the given radius", () => {
    // 30 min walk at 4.5 km/h = 2.25 km radius
    const s = isochroneStats(ROOMS, { lat: 23.75, lng: 90.37 }, 2.25);
    expect(s.count).toBe(2);
  });
});

describe("popup HTML", () => {
  it("escapes user-provided names", () => {
    const html = landmarkPopupHtml(
      "university",
      "U <b>X</b> & Co",
      { count: 1, avgRent: 9000, minRent: 9000, maxRent: 9000 },
      "CTA"
    );
    expect(html).toContain("U &lt;b&gt;X&lt;/b&gt; &amp; Co");
    expect(html).not.toContain("<b>X</b>");
  });

  it("shows honest empty state instead of invented numbers", () => {
    const html = heatmapPopupHtml("Dhanmondi", {
      count: 0,
      avgRent: null,
      minRent: null,
      maxRent: null,
    });
    expect(html).toContain("No rentals here yet");
    expect(html).toContain("Average rent —");
  });

  it("renders a metro-route popup without stats", () => {
    expect(metroRoutePopupHtml()).toContain("MRT Line 6");
  });

  it("renders isochrone popup with minutes", () => {
    const html = isochronePopupHtml(20, {
      count: 3,
      avgRent: 10000,
      minRent: 8000,
      maxRent: 20000,
    });
    expect(html).toContain("20-min walking zone");
    expect(html).toContain("3</b> rooms nearby");
  });
});

describe("formatRent", () => {
  it("formats with taka symbol and thousand separators", () => {
    expect(formatRent(12345)).toBe("৳12,345");
    expect(formatRent(null)).toBe("—");
  });
});

describe("dark-theme paint map (Phase 7 v3 contrast QA)", () => {
  it("exposes every layer's dark/light values", () => {
    expect(Object.keys(THEME_PAINTS).length).toBeGreaterThanOrEqual(8);
    // Landmark dots brighten in dark so they don't sink into the basemap.
    expect(themePaintValue("universities", "circle-color", true)).toBe("#a78bfa");
    expect(themePaintValue("universities", "circle-color", false)).toBe("#7c3aed");
    expect(themePaintValue("metro", "circle-color", true)).toBe("#2dd4bf");
  });

  it("brightens the MRT corridor core on dark", () => {
    expect(themePaintValue("metro-route", "line-color", true)).toBe("#2dd4bf");
    expect(themePaintValue("metro-route", "line-color", false)).toBe("#0d9488");
  });

  it("uses dark-friendly heatmap colors + higher opacity on dark", () => {
    const darkColor = themePaintValue("price-heatmap", "circle-color", true) as unknown[];
    expect(darkColor).toContain("#4ade80"); // green-400 instead of green-500
    expect(themePaintValue("price-heatmap", "circle-opacity", true)).toBe(0.6);
    expect(themePaintValue("price-heatmap", "circle-opacity", false)).toBe(0.45);
    expect(themePaintValue("price-heatmap", "circle-stroke-color", true)).toBe("#111827");
  });

  it("keeps isochrone bands visible on dark with stronger fills", () => {
    expect(TRAVEL_BAND_DARK_OPACITY).toBeGreaterThan(TRAVEL_BAND_LIGHT_OPACITY);
    expect(TRAVEL_BAND_DARK_OPACITY).toBe(0.22);
  });

  it("returns undefined for unknown layer/prop", () => {
    expect(themePaintValue("does-not-exist", "circle-color", true)).toBeUndefined();
    expect(themePaintValue("universities", "line-color", true)).toBeUndefined();
  });
});
