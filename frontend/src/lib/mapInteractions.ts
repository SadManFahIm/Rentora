import type { LandmarkKind, Room } from "../types";
import { haversineKm } from "./mapUtils";

/**
 * Pure helpers behind the map's interaction popups (Phase 7 v3).
 *
 * Every number shown comes from the ACTUAL rooms in the current viewport
 * (roomsRef) — no fabricated counts or rents. When no data exists the popup
 * says so instead of inventing values.
 */

export interface NearbyStats {
  count: number;
  avgRent: number | null;
  minRent: number | null;
  maxRent: number | null;
}

/** Stats for rooms within `radiusKm` of a point (landmarks, radius search). */
export function nearbyStats(
  rooms: Room[],
  lat: number,
  lng: number,
  radiusKm: number
): NearbyStats {
  const within = rooms.filter((r) => haversineKm(lat, lng, r.lat, r.lng) <= radiusKm);
  return priceStats(within);
}

/** Stats for rooms in a single area (heatmap / area popups). */
export function areaStats(rooms: Room[], area: string): NearbyStats {
  return priceStats(rooms.filter((r) => r.area.toLowerCase() === area.toLowerCase()));
}

/**
 * Per-kind landmark metadata — color, dark color, popup icon and label.
 * Single source of truth for both the map layers and the popups, so the
 * category identity can't drift between paint and copy.
 */
export const LANDMARK_KIND_META: Record<
  LandmarkKind,
  { color: string; darkColor: string; icon: string; label: string; minzoom: number }
> = {
  university: {
    color: "#7c3aed",
    darkColor: "#a78bfa",
    icon: "🎓",
    label: "University",
    minzoom: 8,
  },
  metro: { color: "#0d9488", darkColor: "#2dd4bf", icon: "🚇", label: "Metro station", minzoom: 8 },
  hospital: { color: "#e11d48", darkColor: "#fb7185", icon: "🏥", label: "Hospital", minzoom: 9.5 },
  market: { color: "#f59e0b", darkColor: "#fbbf24", icon: "🛒", label: "Market", minzoom: 10.5 },
  park: { color: "#16a34a", darkColor: "#4ade80", icon: "🌳", label: "Park", minzoom: 10.5 },
  mosque: { color: "#0891b2", darkColor: "#22d3ee", icon: "🕌", label: "Mosque", minzoom: 11 },
  bus_terminal: {
    color: "#4f46e5",
    darkColor: "#818cf8",
    icon: "🚌",
    label: "Bus terminal",
    minzoom: 11,
  },
};

/** The zoom at which a category's dots begin showing (declutter at low zoom). */
export function landmarkMinzoom(kind: LandmarkKind): number {
  return LANDMARK_KIND_META[kind]?.minzoom ?? 8;
}

/** Stats for rooms inside an isochrone band radius (walking-time model). */
export function isochroneStats(
  rooms: Room[],
  center: { lat: number; lng: number },
  radiusKm: number
): NearbyStats {
  return nearbyStats(rooms, center.lat, center.lng, radiusKm);
}

function priceStats(rooms: Room[]): NearbyStats {
  const prices = rooms.map((r) => r.price).sort((a, b) => a - b);
  if (prices.length === 0) return { count: 0, avgRent: null, minRent: null, maxRent: null };
  const avg = Math.round(prices.reduce((s, p) => s + p, 0) / prices.length);
  return {
    count: prices.length,
    avgRent: avg,
    minRent: prices[0],
    maxRent: prices[prices.length - 1],
  };
}

export function formatRent(n: number | null): string {
  return n == null ? "—" : `৳${n.toLocaleString()}`;
}

function statsBlock(stats: NearbyStats): string {
  if (stats.count === 0) {
    return `<div class="map-popup__meta">No rentals here yet</div>`;
  }
  return `<div class="map-popup__meta">
    <b>${stats.count}</b> room${stats.count === 1 ? "" : "s"} nearby · avg ${formatRent(stats.avgRent)}
    <br/>range ${formatRent(stats.minRent)}–${formatRent(stats.maxRent)}
  </div>`;
}

/** Popup for any landmark kind (university/metro/hospital/market/…). */
export function landmarkPopupHtml(
  kind: LandmarkKind,
  name: string,
  stats: NearbyStats,
  ctaLabel: string
): string {
  const icon = LANDMARK_KIND_META[kind]?.icon ?? "📍";
  return `
    <div class="map-popup">
      <div class="map-popup__name">${icon} ${esc(name)}</div>
      <div class="map-popup__meta">${LANDMARK_KIND_META[kind]?.label ?? "Place"}</div>
      ${statsBlock(stats)}
      <div class="map-popup__cta" data-map-cta="nearby">${ctaLabel}</div>
    </div>
  `;
}

/** Popup for the MRT Line-6 corridor (no per-listing stats). */
export function metroRoutePopupHtml(): string {
  return `
    <div class="map-popup">
      <div class="map-popup__name">🚇 MRT Line 6</div>
      <div class="map-popup__meta">Uttara North → Motijheel · click a station dot for nearby rentals</div>
    </div>
  `;
}

/** Popup for a price-heatmap click — shows the clicked area's real stats. */
export function heatmapPopupHtml(area: string, stats: NearbyStats): string {
  return `
    <div class="map-popup">
      <div class="map-popup__name">📍 ${esc(area)}</div>
      <div class="map-popup__meta">Average rent ${formatRent(stats.avgRent)}</div>
      ${statsBlock(stats)}
    </div>
  `;
}

/** Popup for an isochrone (walking-zone) band click. */
export function isochronePopupHtml(minutes: number, stats: NearbyStats): string {
  return `
    <div class="map-popup">
      <div class="map-popup__name">🚶 ${minutes}-min walking zone</div>
      ${statsBlock(stats)}
    </div>
  `;
}

function esc(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ============================================================
// NEARBY LANDMARK CHIPS (Phase 7 v3 — listing popups)
// ============================================================
// A listing popup shows the nearest useful places around it as compact
// chips (🚇 7 min Metro · 🎓 12 min University). Only categories with an
// actual landmark within the cap are shown — no invented places. Distances
// are straight-line haversine km converted to a rough walk time; they're
// clearly walk estimates, not navigation routes.

export interface NearbyLandmarkChip {
  kind: LandmarkKind;
  name: string;
  key: string;
  distanceKm: number;
  walkMinutes: number;
}

/** Landmarks near a point, one per category (nearest first), capped by km. */
export function nearbyLandmarkChips(
  landmarks: { key: string; name: string; kind: LandmarkKind; lat: number; lng: number }[],
  lat: number,
  lng: number,
  maxKm = 3
): NearbyLandmarkChip[] {
  const byKind = new Map<LandmarkKind, { lm: (typeof landmarks)[number]; km: number }>();
  landmarks.forEach((lm) => {
    const km = haversineKm(lat, lng, lm.lat, lm.lng);
    const best = byKind.get(lm.kind);
    if (km <= maxKm && (!best || km < best.km)) {
      byKind.set(lm.kind, { lm, km });
    }
  });
  return [...byKind.values()]
    .map(({ lm, km }) => ({
      kind: lm.kind,
      name: lm.name,
      key: lm.key,
      distanceKm: km,
      walkMinutes: Math.max(1, Math.round((km / 4.5) * 60)),
    }))
    .sort((a, b) => a.distanceKm - b.distanceKm);
}

/** HTML for the nearby-landmark chip row inside a listing popup. */
export function nearbyLandmarkChipsHtml(
  landmarks: { key: string; name: string; kind: LandmarkKind; lat: number; lng: number }[],
  lat: number,
  lng: number,
  maxKm = 3
): string {
  const chips = nearbyLandmarkChips(landmarks, lat, lng, maxKm);
  if (chips.length === 0) return "";
  const rows = chips
    .map(
      (c) =>
        `<button type="button" class="map-popup__chip" data-chip-key="${esc(c.key)}" data-chip-kind="${c.kind}" title="${esc(c.name)}">` +
        `${LANDMARK_KIND_META[c.kind]?.icon ?? "📍"} ${c.walkMinutes} min ${LANDMARK_KIND_META[c.kind]?.label ?? c.kind}` +
        `</button>`
    )
    .join("");
  return `<div class="map-popup__nearby"><span class="map-popup__nearby-label">Nearby</span><div class="map-popup__chips">${rows}</div></div>`;
}

// ============================================================
// ZOOM-AWARE AREA LABELS (Phase 7 v3 — geographic labels)
// ============================================================
// Boundary bubbles carry their area's real centre (lat/lng). The map turns
// those into symbol-layer labels with zoom-based visibility + priority so
// the map never drowns in text: main areas from z≈10, sub-areas from
// z≈12.5, neighbourhoods from z≈14.5. Text stays readable in both themes
// via THEME_PAINTS (light text + dark halo on dark, dark text + white halo
// on light).

/** A GeoJSON Point feature for one area's label. */
export function areaLabelFeature(area: {
  key: string;
  name: string;
  kind: string;
  parent?: string | null;
  parent_name?: string | null;
  lat: number;
  lng: number;
}): GeoJSON.Feature {
  return {
    type: "Feature",
    geometry: { type: "Point", coordinates: [area.lng, area.lat] },
    properties: {
      key: area.key,
      name: area.name,
      kind: area.kind,
      parent: area.parent ?? null,
      parent_name: area.parent_name ?? null,
    },
  };
}

/** FeatureCollection of label points from the boundary bubbles endpoint. */
export function boundaryLabelsToFeatureCollection(boundaries: {
  type: "FeatureCollection";
  features: { properties?: Record<string, unknown> | null }[];
}): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: boundaries.features
      .map((f) => {
        const p = (f.properties ?? {}) as Record<string, unknown>;
        const lat = Number(p.lat);
        const lng = Number(p.lng);
        if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
        return areaLabelFeature({
          key: String(p.key ?? ""),
          name: String(p.name ?? ""),
          kind: String(p.kind ?? ""),
          parent: p.parent as string | null | undefined,
          parent_name: p.parent_name as string | null | undefined,
          lat,
          lng,
        });
      })
      .filter((f): f is GeoJSON.Feature => f !== null),
  };
}

/** Zoom at which each area-kind label appears (priority by hierarchy). */
export const AREA_LABEL_MINZOOM: Record<string, number> = {
  main_area: 10,
  sub_area: 12.5,
  neighborhood: 14.5,
};

// ============================================================
// AREA BOUNDARY PAINTS (feature-state + theme aware)
// ============================================================
// Boundary bubbles highlight via MapLibre feature-state (hover/selected).
// Because the highlight lives INSIDE a paint expression, a theme swap must
// re-apply the same expression with the theme's colors — a flat color would
// silently kill the hover/selected states. These builders return the full
// expression for a given theme so the initial layer paint and the
// THEME_PAINTS swap use identical logic (unit-tested).

export type BoundaryKind = "main_area" | "sub_area" | "neighborhood";

/** Per-kind line colors per state; `dark`/`light` per theme. */
export const AREA_BOUNDARY_LINE_COLORS: Record<
  BoundaryKind,
  Record<"selected" | "hover" | "base", { dark: string; light: string }>
> = {
  main_area: {
    // Selected = deepest orange on light (locked-in), palest on dark
    // (brightest against near-black) so it always reads as "active".
    selected: { dark: "#fed7aa", light: "#7c2d12" },
    hover: { dark: "#fdba74", light: "#f97316" },
    base: { dark: "#fb923c", light: "#ea580c" },
  },
  sub_area: {
    selected: { dark: "#bfdbfe", light: "#1e40af" },
    hover: { dark: "#93c5fd", light: "#60a5fa" },
    base: { dark: "#60a5fa", light: "#3b82f6" },
  },
  neighborhood: {
    selected: { dark: "#ddd6fe", light: "#5b21b6" },
    hover: { dark: "#c4b5fd", light: "#8b5cf6" },
    base: { dark: "#a78bfa", light: "#7c3aed" },
  },
};

/** Per-kind fill opacities per state as [dark, light]. */
export const AREA_BOUNDARY_FILL_OPACITIES: Record<
  BoundaryKind,
  Record<"selected" | "hover" | "base", [number, number]>
> = {
  main_area: { selected: [0.22, 0.18], hover: [0.15, 0.12], base: [0.08, 0.06] },
  sub_area: { selected: [0.2, 0.16], hover: [0.13, 0.1], base: [0.07, 0.05] },
  neighborhood: { selected: [0.19, 0.15], hover: [0.12, 0.09], base: [0.06, 0.04] },
};

/** Full `line-color` expression for a boundary kind + theme. */
export function areaBoundaryLineColor(kind: BoundaryKind, dark: boolean): unknown {
  const c = AREA_BOUNDARY_LINE_COLORS[kind];
  const pick = (state: keyof typeof c) => (dark ? c[state].dark : c[state].light);
  return [
    "case",
    ["==", ["feature-state", "selected"], true],
    pick("selected"),
    ["==", ["feature-state", "hover"], true],
    pick("hover"),
    pick("base"),
  ];
}

/** Full `fill-opacity` expression for a boundary kind + theme. */
export function areaBoundaryFillOpacity(kind: BoundaryKind, dark: boolean): unknown {
  const c = AREA_BOUNDARY_FILL_OPACITIES[kind];
  const pick = (state: keyof typeof c) => (dark ? c[state][0] : c[state][1]);
  return [
    "case",
    ["==", ["feature-state", "selected"], true],
    pick("selected"),
    ["==", ["feature-state", "hover"], true],
    pick("hover"),
    pick("base"),
  ];
}

// ============================================================
// DARK-THEME LAYER PAINTS (Phase 7 v3 — visual QA)
// ============================================================
// MapLibre layers are created with light-tuned paints; when the app switches
// to dark mode we re-paint them via setPaintProperty. This map is the single
// source of truth for those values — kept here (pure data) so the contrast
// choices are unit-testable and consistent between the theme-swap effect and
// any future layer. ``undefined`` means "leave the layer's current value" —
// the theme-swap effect skips it.

export interface ThemePaintPatch {
  /** Property name passed to map.setPaintProperty (typed at the call site). */
  prop: string;
  /** Paint value for dark mode. */
  dark: unknown;
  /** Paint value for light mode. */
  light: unknown;
}

/** Layer → theme-aware paint patches applied on dark/light toggle. */
export const THEME_PAINTS: Record<string, ThemePaintPatch[]> = {
  universities: [
    { prop: "circle-color", dark: "#a78bfa", light: "#7c3aed" },
    { prop: "circle-stroke-color", dark: "#2b1b4d", light: "#ffffff" },
  ],
  metro: [
    { prop: "circle-color", dark: "#2dd4bf", light: "#0d9488" },
    { prop: "circle-stroke-color", dark: "#0b3a35", light: "#ffffff" },
  ],
  "metro-route": [{ prop: "line-color", dark: "#2dd4bf", light: "#0d9488" }],
  "metro-route-casing": [
    { prop: "line-color", dark: "#134e4a", light: "#ffffff" },
    { prop: "line-opacity", dark: 0.5, light: 0.55 },
  ],
  // Everyday places (hospital/market/park/mosque/bus_terminal) — brighter
  // dots + dark strokes on the dark basemap, same as universities/metro.
  "places-hospital": [
    { prop: "circle-color", dark: "#fb7185", light: "#e11d48" },
    { prop: "circle-stroke-color", dark: "#4c0519", light: "#ffffff" },
  ],
  "places-market": [
    { prop: "circle-color", dark: "#fbbf24", light: "#f59e0b" },
    { prop: "circle-stroke-color", dark: "#451a03", light: "#ffffff" },
  ],
  "places-park": [
    { prop: "circle-color", dark: "#4ade80", light: "#16a34a" },
    { prop: "circle-stroke-color", dark: "#052e16", light: "#ffffff" },
  ],
  "places-mosque": [
    { prop: "circle-color", dark: "#22d3ee", light: "#0891b2" },
    { prop: "circle-stroke-color", dark: "#083344", light: "#ffffff" },
  ],
  "places-bus-terminal": [
    { prop: "circle-color", dark: "#818cf8", light: "#4f46e5" },
    { prop: "circle-stroke-color", dark: "#1e1b4b", light: "#ffffff" },
  ],
  "places-clusters-layer": [{ prop: "circle-stroke-color", dark: "#134e4a", light: "#ffffff" }],
  "price-heatmap": [
    {
      prop: "circle-color",
      dark: [
        "interpolate",
        ["linear"],
        ["get", "price"],
        5000,
        "#4ade80",
        15000,
        "#fbbf24",
        30000,
        "#f87171",
      ],
      light: [
        "interpolate",
        ["linear"],
        ["get", "price"],
        5000,
        "#22c55e",
        15000,
        "#f59e0b",
        30000,
        "#ef4444",
      ],
    },
    { prop: "circle-opacity", dark: 0.6, light: 0.45 },
    { prop: "circle-stroke-color", dark: "#111827", light: "#ffffff" },
  ],
  "rooms-clusters-layer": [{ prop: "circle-stroke-color", dark: "#7c2d12", light: "#ffffff" }],
  "rooms-unclustered-point": [{ prop: "circle-stroke-color", dark: "#111827", light: "#ffffff" }],
  "radius-circle": [
    { prop: "circle-opacity", dark: 0.18, light: 0.12 },
    { prop: "circle-stroke-color", dark: "#60a5fa", light: "#3b82f6" },
  ],
  "metro-reach": [
    { prop: "circle-color", dark: "#2dd4bf", light: "#0d9488" },
    { prop: "circle-stroke-color", dark: "#134e4a", light: "#ffffff" },
  ],
  // Area boundary bubbles — brighter strokes on dark so the rings read
  // against the near-black basemap; fills stay whisper-light either way.
  // NOTE: line-color / fill-opacity carry the feature-state highlight
  // (selected/hover) INSIDE the expression, so the dark/light values here
  // are full expressions (areaBoundaryLineColor/FillOpacity), never flat
  // colors — a flat color would erase the hover/selected states.
  "area-boundary-line-main": [
    {
      prop: "line-color",
      dark: areaBoundaryLineColor("main_area", true),
      light: areaBoundaryLineColor("main_area", false),
    },
    { prop: "line-opacity", dark: 0.85, light: 0.75 },
  ],
  "area-boundary-fill-main": [
    {
      prop: "fill-opacity",
      dark: areaBoundaryFillOpacity("main_area", true),
      light: areaBoundaryFillOpacity("main_area", false),
    },
  ],
  "area-boundary-line-sub": [
    {
      prop: "line-color",
      dark: areaBoundaryLineColor("sub_area", true),
      light: areaBoundaryLineColor("sub_area", false),
    },
    { prop: "line-opacity", dark: 0.75, light: 0.6 },
  ],
  "area-boundary-fill-sub": [
    {
      prop: "fill-opacity",
      dark: areaBoundaryFillOpacity("sub_area", true),
      light: areaBoundaryFillOpacity("sub_area", false),
    },
  ],
  "area-boundary-line-nbhd": [
    {
      prop: "line-color",
      dark: areaBoundaryLineColor("neighborhood", true),
      light: areaBoundaryLineColor("neighborhood", false),
    },
    { prop: "line-opacity", dark: 0.65, light: 0.5 },
  ],
  "area-boundary-fill-nbhd": [
    {
      prop: "fill-opacity",
      dark: areaBoundaryFillOpacity("neighborhood", true),
      light: areaBoundaryFillOpacity("neighborhood", false),
    },
  ],
  // Zoom-aware area labels — the text the user actually complained about:
  // the layers were created with LIGHT-tuned dark-gray text, and without
  // these entries the theme swap never re-painted them, leaving area names
  // invisible on the dark basemap. Dark = near-white text with a dark halo
  // (reads on CARTO's dark tiles); light = dark text with a white halo.
  "area-label-main": [
    { prop: "text-color", dark: "#f8fafc", light: "#1f2937" },
    { prop: "text-halo-color", dark: "#111827", light: "#ffffff" },
  ],
  "area-label-sub": [
    { prop: "text-color", dark: "#e2e8f0", light: "#4b5563" },
    { prop: "text-halo-color", dark: "#111827", light: "#ffffff" },
  ],
  "area-label-nbhd": [
    { prop: "text-color", dark: "#e2e8f0", light: "#4b5563" },
    { prop: "text-halo-color", dark: "#111827", light: "#ffffff" },
  ],
};

/** Travel-band layers get stronger fills on dark (0.1 is invisible there). */
export const TRAVEL_BAND_DARK_OPACITY = 0.22;
export const TRAVEL_BAND_LIGHT_OPACITY = 0.1;

/** Resolve the paint value for a layer+prop in the given theme. */
export function themePaintValue(layer: string, prop: string, dark: boolean): unknown | undefined {
  const patches = THEME_PAINTS[layer];
  const patch = patches?.find((p) => p.prop === prop);
  return patch ? (dark ? patch.dark : patch.light) : undefined;
}
