import { describe, expect, it } from "vitest";
import {
  AREA_BOUNDARY_LINE_COLORS,
  areaBoundaryFillOpacity,
  areaBoundaryLineColor,
  AREA_LABEL_MINZOOM,
  areaStats,
  formatRent,
  heatmapPopupHtml,
  isochronePopupHtml,
  isochroneStats,
  LANDMARK_KIND_META,
  landmarkMinzoom,
  landmarkPopupHtml,
  metroRoutePopupHtml,
  nearbyLandmarkChips,
  nearbyLandmarkChipsHtml,
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

describe("landmark kind metadata", () => {
  it("covers every category with an icon, label, color and minzoom", () => {
    const kinds = [
      "university",
      "metro",
      "hospital",
      "market",
      "park",
      "mosque",
      "bus_terminal",
    ] as const;
    kinds.forEach((kind) => {
      const meta = LANDMARK_KIND_META[kind];
      expect(meta.icon).toBeTruthy();
      expect(meta.label).toBeTruthy();
      expect(meta.color).toMatch(/^#[0-9a-f]{6}$/i);
      expect(meta.darkColor).toMatch(/^#[0-9a-f]{6}$/i);
      expect(meta.minzoom).toBeGreaterThanOrEqual(8);
    });
  });

  it("declutters the map: dense everyday categories appear later than universities/metro", () => {
    // Universities + metro are core wayfinding — always visible; the
    // everyday categories appear progressively as you zoom in so the map
    // doesn't drown in dots at city level.
    expect(landmarkMinzoom("university")).toBeLessThan(landmarkMinzoom("market"));
    expect(landmarkMinzoom("metro")).toBeLessThan(landmarkMinzoom("bus_terminal"));
    expect(landmarkMinzoom("market")).toBeLessThanOrEqual(landmarkMinzoom("mosque"));
  });

  it("renders the everyday-category label in the popup", () => {
    const html = landmarkPopupHtml(
      "hospital",
      "Shaheed Suhrawardy Hospital",
      { count: 2, avgRent: 10000, minRent: 8000, maxRent: 12000 },
      "Rooms near here →"
    );
    expect(html).toContain("🏥");
    expect(html).toContain("Hospital");
    expect(html).toContain("2</b> rooms nearby");
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

  it("keeps the boundary highlight INSIDE the theme paint (feature-state)", () => {
    // Regression: a theme swap must re-apply the full case expression, not a
    // flat color — a flat color would silently erase the hover/selected
    // states. The dark/light values must BE expressions starting with "case".
    const darkLine = themePaintValue("area-boundary-line-main", "line-color", true) as unknown[];
    const lightLine = themePaintValue("area-boundary-line-main", "line-color", false) as unknown[];
    expect(darkLine[0]).toBe("case");
    expect(lightLine[0]).toBe("case");
    const darkFill = themePaintValue("area-boundary-fill-main", "fill-opacity", true) as unknown[];
    expect(darkFill[0]).toBe("case");
    // And the selected color inside the dark expression must be the bright
    // one (readable on the near-black basemap), not the dark gray base.
    expect(darkLine).toContain("#fed7aa");
    expect(lightLine).toContain("#7c2d12");
  });

  it("area labels are theme-aware (dark text readable on dark tiles)", () => {
    // Regression for the reported dark-mode bug: the label layers were
    // created with dark-gray text that was never re-painted, so area names
    // were invisible on the dark basemap. THEME_PAINTS must carry per-theme
    // text colors + halos for every label kind.
    expect(themePaintValue("area-label-main", "text-color", true)).toBe("#f8fafc");
    expect(themePaintValue("area-label-main", "text-color", false)).toBe("#1f2937");
    expect(themePaintValue("area-label-main", "text-halo-color", true)).toBe("#111827");
    expect(themePaintValue("area-label-main", "text-halo-color", false)).toBe("#ffffff");
    expect(themePaintValue("area-label-sub", "text-color", true)).toBe("#e2e8f0");
    expect(themePaintValue("area-label-nbhd", "text-color", true)).toBe("#e2e8f0");
    // Zoom-aware hierarchy: main areas first, then sub-areas, then
    // neighbourhoods — never all at once.
    expect(AREA_LABEL_MINZOOM.main_area).toBeLessThan(AREA_LABEL_MINZOOM.sub_area);
    expect(AREA_LABEL_MINZOOM.sub_area).toBeLessThan(AREA_LABEL_MINZOOM.neighborhood);
  });

  it("returns undefined for unknown layer/prop", () => {
    expect(themePaintValue("does-not-exist", "circle-color", true)).toBeUndefined();
    expect(themePaintValue("universities", "line-color", true)).toBeUndefined();
  });
});

describe("area boundary paint builders (feature-state + theme)", () => {
  it("returns a case expression ordering selected > hover > base", () => {
    const expr = areaBoundaryLineColor("main_area", true) as unknown[];
    expect(expr[0]).toBe("case");
    expect(expr[1]).toEqual(["==", ["feature-state", "selected"], true]);
    expect(expr[3]).toEqual(["==", ["feature-state", "hover"], true]);
  });

  it("uses the theme's palette inside the expression", () => {
    const dark = areaBoundaryLineColor("main_area", true) as unknown[];
    const light = areaBoundaryLineColor("main_area", false) as unknown[];
    // Selected is brightest on dark, deepest on light.
    expect(dark).toContain(AREA_BOUNDARY_LINE_COLORS.main_area.selected.dark);
    expect(light).toContain(AREA_BOUNDARY_LINE_COLORS.main_area.selected.light);
    expect(AREA_BOUNDARY_LINE_COLORS.main_area.selected.dark).toBe("#fed7aa");
  });

  it("raises fill opacity for selected/hover and in dark mode", () => {
    const dark = areaBoundaryFillOpacity("main_area", true) as number[];
    const light = areaBoundaryFillOpacity("main_area", false) as number[];
    // dark[2] = selected opacity, dark[4] = hover, dark[5] = base.
    expect(dark[2]).toBeGreaterThan(dark[4]);
    expect(dark[4]).toBeGreaterThan(dark[5]);
    expect(dark[5]).toBeGreaterThan(light[5]); // dark fills a bit stronger
  });
});

describe("nearby landmark chips (Phase 7 v3 — listing popup)", () => {
  const LANDMARKS = [
    { key: "mrt_uttara_north", name: "Uttara North", kind: "metro", lat: 23.76, lng: 90.38 },
    { key: "mrt_mirpur_10", name: "Mirpur 10", kind: "metro", lat: 23.755, lng: 90.375 },
    { key: "du", name: "University of Dhaka", kind: "university", lat: 23.745, lng: 90.372 },
    { key: "new_market", name: "New Market", kind: "market", lat: 23.74, lng: 90.375 },
    { key: "far_park", name: "Far Park", kind: "park", lat: 24.1, lng: 90.5 }, // beyond cap
  ] as const;

  it("returns the nearest landmark per category, sorted by distance, capped by km", () => {
    // Reference point (23.75, 90.37): nearest = DU (university) ~0.6 km,
    // then Mirpur 10 (metro) ~0.8 km, then New Market (market) ~1.2 km.
    const chips = nearbyLandmarkChips(LANDMARKS as unknown as never[], 23.75, 90.37, 3);
    const kinds = chips.map((c) => c.kind);
    expect(kinds).toEqual(["university", "metro", "market"]); // nearest first
    // Far Park is beyond 3 km — never invented into the list.
    expect(kinds).not.toContain("park");
    // One chip per category — the nearest metro wins (Mirpur 10 beats
    // Uttara North); no duplicate category chips.
    expect(chips.filter((c) => c.kind === "metro")).toHaveLength(1);
    expect(chips.find((c) => c.kind === "metro")?.key).toBe("mrt_mirpur_10");
  });

  it("estimates walk time from straight-line km (labelled as an estimate)", () => {
    const chips = nearbyLandmarkChips(LANDMARKS as unknown as never[], 23.75, 90.37, 3);
    const uni = chips.find((c) => c.kind === "university")!;
    expect(uni.walkMinutes).toBeGreaterThan(0);
    expect(uni.distanceKm).toBeGreaterThan(0);
  });

  it("renders chips with accessible labels (screen readers skip the emoji)", () => {
    const html = nearbyLandmarkChipsHtml(LANDMARKS as unknown as never[], 23.75, 90.37, 3);
    expect(html).toContain('aria-label="');
    // The emoji icon is hidden from the accessibility tree; the name + walk
    // time is what a screen reader announces.
    expect(html).toContain('aria-hidden="true"');
    expect(html).toContain("min University");
  });

  it("returns empty HTML when nothing is within the cap (no invented places)", () => {
    const html = nearbyLandmarkChipsHtml(LANDMARKS as unknown as never[], 24.2, 90.6, 1);
    expect(html).toBe("");
  });
});

describe("zoom-aware label hierarchy (Phase 7 v3 — decluttering)", () => {
  it("reveals labels progressively: main areas first, then sub, then neighbourhoods", () => {
    expect(AREA_LABEL_MINZOOM.main_area).toBeLessThan(AREA_LABEL_MINZOOM.sub_area);
    expect(AREA_LABEL_MINZOOM.sub_area).toBeLessThan(AREA_LABEL_MINZOOM.neighborhood);
  });

  it("landmark categories also declutter by zoom (dots only when meaningful)", () => {
    // Universities/metro are always useful; small categories appear later.
    expect(landmarkMinzoom("university")).toBeLessThanOrEqual(landmarkMinzoom("hospital"));
    expect(landmarkMinzoom("hospital")).toBeLessThan(landmarkMinzoom("mosque"));
  });
});
