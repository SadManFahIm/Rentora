import type { Room } from "../types";
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

/** Popup for a university or metro station click. */
export function landmarkPopupHtml(
  kind: "university" | "metro",
  name: string,
  stats: NearbyStats,
  ctaLabel: string
): string {
  const icon = kind === "university" ? "🎓" : "🚇";
  return `
    <div class="map-popup">
      <div class="map-popup__name">${icon} ${esc(name)}</div>
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
