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
