// ============================================================
// MAP UTILITIES — pure helpers for the MapLibre map view (Phase 7)
// ============================================================

import type { Landmark, Room } from "../types";

export interface LngLatBounds {
  west: number;
  south: number;
  east: number;
  north: number;
}

/**
 * Build the backend's `bbox` query value from a map viewport, in GeoJSON
 * order (minLng,minLat,maxLng,maxLat) as the API expects.
 */
export function buildBbox(bounds: LngLatBounds): string {
  return [bounds.west, bounds.south, bounds.east, bounds.north]
    .map((v) => (Number.isFinite(v) ? v : 0).toFixed(6))
    .join(",");
}

/**
 * Quantize a viewport's corners *outward* to ~100 m (3 decimal places) so
 * micro-pans between effectively-identical viewports hit the query cache
 * instead of refetching. Rounding outward (floor on west/south, ceil on
 * east/north) means the quantized box always *contains* the visible one —
 * a room on the visible edge can never be dropped from the results.
 */
export function quantizeBounds(bounds: LngLatBounds): LngLatBounds {
  return {
    west: Math.floor(bounds.west * 1000) / 1000,
    south: Math.floor(bounds.south * 1000) / 1000,
    east: Math.ceil(bounds.east * 1000) / 1000,
    north: Math.ceil(bounds.north * 1000) / 1000,
  };
}

/** A room as a GeoJSON Feature for MapLibre GeoJSON sources. */
export function roomToFeature(room: Room): GeoJSON.Feature {
  return {
    type: "Feature",
    geometry: {
      type: "Point",
      coordinates: [room.lng, room.lat],
    },
    properties: {
      id: room.id,
      name: room.name,
      price: room.price,
      area: room.area,
      tier: room.tier,
      available: room.available,
      verified: room.verified,
      rating: room.rating,
      reviews: room.reviews,
    },
  };
}

/** All rooms as a single GeoJSON FeatureCollection. */
export function roomsToFeatureCollection(rooms: Room[]): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: rooms.map(roomToFeature),
  };
}

/** A landmark as a GeoJSON Feature (used for layer-based toggles). */
export function landmarkToFeature(landmark: Landmark): GeoJSON.Feature {
  return {
    type: "Feature",
    geometry: { type: "Point", coordinates: [landmark.lng, landmark.lat] },
    properties: { name: landmark.name, kind: landmark.kind },
  };
}

export function landmarksToFeatureCollection(landmarks: Landmark[]): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: landmarks.map(landmarkToFeature),
  };
}

/**
 * Metro-route polyline: a single LineString threading the metro stations
 * north-to-south (MRT Line 6 runs Uttara → Motijheel), so the map can draw
 * the rail corridor the stations sit on — not just isolated dots. The
 * stations in `landmarks` are unordered, so we sort by latitude first.
 */
export function metroRouteFeatureCollection(metroStations: Landmark[]): GeoJSON.FeatureCollection {
  const ordered = [...metroStations].sort((a, b) => b.lat - a.lat);
  if (ordered.length < 2) {
    return { type: "FeatureCollection", features: [] };
  }
  return {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        geometry: {
          type: "LineString",
          coordinates: ordered.map((s) => [s.lng, s.lat]),
        },
        properties: { name: "MRT Line 6" },
      },
    ],
  };
}

/**
 * Marker + heatmap colour for a room's tier. Free listings get the brand
 * orange; paid promotions get distinct accent colours so promoted rooms pop
 * on the map exactly like they do in the list.
 */
export function tierColor(tier: Room["tier"]): string {
  switch (tier) {
    case "premium":
      return "#f59e0b"; // amber — premium
    case "featured":
      return "#3b82f6"; // blue — featured
    default:
      return "#ea580c"; // orange — free
  }
}

/**
 * CSS class for the map marker pin. Mirrors the tier badges used on cards so
 * the map and the list speak the same visual language.
 */
export function markerClassName(tier: Room["tier"]): string {
  switch (tier) {
    case "premium":
      return "map-marker map-marker--premium";
    case "featured":
      return "map-marker map-marker--featured";
    default:
      return "map-marker";
  }
}

/** Compact price label shown inside a marker pin. */
export function markerPrice(price: number): string {
  return price >= 1000 ? `৳${Math.round(price / 1000)}k` : `৳${price}`;
}

/** Sum of prices / count — small stat for the map toolbar. */
export function avgPrice(rooms: Room[]): number | null {
  if (rooms.length === 0) return null;
  return Math.round(rooms.reduce((sum, r) => sum + r.price, 0) / rooms.length);
}

/**
 * Decide whether clustering is worthwhile: with few listings individual pins
 * are clearer; past this threshold clusters keep the map readable.
 */
export function shouldCluster(roomCount: number, threshold = 12): boolean {
  return roomCount >= threshold;
}

/**
 * Sort rooms for the map sidebar: promoted tiers first, then price ascending
 * (cheapest first is the natural browse order), unavailable last.
 */
export function sortRoomsForList(rooms: Room[]): Room[] {
  const rank = (r: Room): number =>
    !r.available ? 3 : r.tier === "premium" ? 0 : r.tier === "featured" ? 1 : 2;
  return [...rooms].sort((a, b) => rank(a) - rank(b) || a.price - b.price);
}

/** Short human-readable summary for the map list panel header. */
export function viewSummary(rooms: Room[]): string {
  const total = rooms.length;
  const available = rooms.filter((r) => r.available).length;
  if (total === 0) return "No rooms in view";
  return `${available} of ${total} room${total === 1 ? "" : "s"} available`;
}

// ============================================================
// SHAREABLE MAP VIEW STATE (Phase 7 — URL-encoded map view)
// ============================================================

/** View state encoded in the map URL so links share the exact map view. */
export interface MapViewParams {
  /** [lat, lng] from `?center=` (comma-separated). */
  center: [number, number] | null;
  /** Zoom level from `?zoom=`, clamped to MapLibre's sane range. */
  zoom: number | null;
  /** Radius search distance in km from `?r=`. */
  radiusKm: number | null;
  /** Radius-search label from `?q=` (the street/area/station name). */
  query: string | null;
  /** Selected listing id from `?room=` (deep link reopens its popup). */
  room: number | null;
  /** Selected area name from `?area=` (boundary click filter). */
  area: string | null;
  /** Landmark category from `?near=` (list-view nearby-landmark filter). */
  near: string | null;
  /** Distance in km from `?distance=` (pairs with `?near=`). */
  distanceKm: number | null;
}

/**
 * Parse `?center=lat,lng&zoom=z&r=km&q=label` from a search string into a
 * typed view. Invalid/missing values become `null` so callers can fall back
 * to their defaults. `center` is returned as [lat, lng] (human order) even
 * though MapLibre consumes [lng, lat].
 */
export function parseMapViewUrl(search: string): MapViewParams {
  const params = new URLSearchParams(search);
  let center: [number, number] | null = null;
  const centerRaw = params.get("center");
  if (centerRaw) {
    const [lat, lng] = centerRaw.split(",").map((v) => Number(v));
    if (
      Number.isFinite(lat) &&
      Number.isFinite(lng) &&
      Math.abs(lat) <= 90 &&
      Math.abs(lng) <= 180
    ) {
      center = [lat, lng];
    }
  }
  const zoom = Number(params.get("zoom"));
  const radiusKm = Number(params.get("r"));
  const query = params.get("q");
  const room = Number(params.get("room"));
  const area = params.get("area");
  const near = params.get("near");
  const distanceKm = Number(params.get("distance"));
  return {
    center,
    zoom: Number.isFinite(zoom) && zoom >= 2 && zoom <= 20 ? zoom : null,
    radiusKm: Number.isFinite(radiusKm) && radiusKm > 0 && radiusKm <= 10 ? radiusKm : null,
    query: query && query.trim().length > 0 ? query.trim().slice(0, 80) : null,
    room: Number.isInteger(room) && room > 0 ? room : null,
    area: area && area.trim().length > 0 ? area.trim().slice(0, 40) : null,
    near: near && near.trim().length > 0 ? near.trim().slice(0, 40) : null,
    distanceKm:
      Number.isFinite(distanceKm) && distanceKm >= 0.25 && distanceKm <= 10 ? distanceKm : null,
  };
}

/**
 * Build the shareable `?center=lat,lng&zoom=z&r=km&q=label` search string for
 * a map view. The mirror of `parseMapViewUrl` — used by the URL-sync effect
 * AND the Share button so a copied link always equals what the URL bar shows
 * (and round-trips through `parseMapViewUrl` losslessly).
 */
export function buildMapViewUrl(view: {
  center: { lat: number; lng: number };
  zoom: number;
  radiusKm?: number | null;
  label?: string | null;
  roomId?: number | null;
  /** Selected area (boundary click) — serialized as `?area=`. */
  area?: string | null;
  /** Landmark category (list-view nearby filter) — serialized as `?near=`. */
  near?: string | null;
  /** Distance in km for the nearby filter — serialized as `?distance=`. */
  distanceKm?: number | null;
}): string {
  // encodeURIComponent keeps commas (unlike URLSearchParams' %2C) so the
  // address stays readable: ?center=23.8103,90.4125&zoom=11.2. parseMapViewUrl
  // reads both forms fine.
  const parts = [`center=${view.center.lat.toFixed(4)},${view.center.lng.toFixed(4)}`];
  parts.push(`zoom=${view.zoom.toFixed(1)}`);
  if (view.radiusKm != null && view.radiusKm > 0 && view.label) {
    parts.push(`r=${view.radiusKm}`, `q=${encodeURIComponent(view.label.slice(0, 80))}`);
  }
  if (view.roomId != null && Number.isInteger(view.roomId) && view.roomId > 0) {
    parts.push(`room=${view.roomId}`);
  }
  if (view.area && view.area.trim().length > 0) {
    parts.push(`area=${encodeURIComponent(view.area.trim().slice(0, 40))}`);
  }
  if (view.near && view.near.trim().length > 0) {
    parts.push(`near=${encodeURIComponent(view.near.trim().slice(0, 40))}`);
  }
  if (view.distanceKm != null && view.distanceKm >= 0.25 && view.distanceKm <= 10) {
    parts.push(`distance=${view.distanceKm}`);
  }
  return `?${parts.join("&")}`;
}

// ============================================================
// DISTANCE + TRAVEL-TIME HELPERS (Phase 7 — travel overlay)
// ============================================================

const EARTH_RADIUS_KM = 6371.0088;

/** Great-circle distance between two points, in km (haversine). */
export function haversineKm(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLng = ((lng2 - lng1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLng / 2) ** 2;
  return 2 * EARTH_RADIUS_KM * Math.asin(Math.sqrt(a));
}

// Typical walking speed used for travel-time estimates (km/h). Dhaka
// streets are congested, so this is a conservative ~4.5 km/h.
const WALKING_SPEED_KMH = 4.5;

/** Walking minutes for a straight-line distance in km. */
export function walkingMinutes(distanceKm: number): number {
  if (distanceKm <= 0) return 0;
  return Math.round((distanceKm / WALKING_SPEED_KMH) * 60);
}

/** "850 m" / "1.2 km" — human-readable distance. */
export function formatDistance(distanceKm: number): string {
  if (distanceKm < 1) return `${Math.round(distanceKm * 1000)} m`;
  return `${distanceKm.toFixed(1)} km`;
}

/** "≈ 12 min walk" travel-time label. */
export function formatTravelTime(distanceKm: number): string {
  const minutes = walkingMinutes(distanceKm);
  if (minutes < 1) return "< 1 min walk";
  return `≈ ${minutes} min walk`;
}

// Typical Dhaka driving speed used for ETA estimates (km/h) — urban traffic
// keeps it far below highway speeds; deliberately conservative.
const DRIVING_SPEED_KMH = 18;

/** Driving minutes for a straight-line distance in km (urban estimate). */
export function drivingMinutes(distanceKm: number): number {
  if (distanceKm <= 0) return 0;
  return Math.round((distanceKm / DRIVING_SPEED_KMH) * 60);
}

/** "≈ 12 min drive" travel-time label. */
export function formatDriveTime(distanceKm: number): string {
  const minutes = drivingMinutes(distanceKm);
  if (minutes < 1) return "< 1 min drive";
  return `≈ ${minutes} min drive`;
}

/** Travel modes the directions deep-link supports (Google Maps travelmode). */
export type TravelMode = "walking" | "driving" | "transit";

/**
 * Google Maps directions deep-link between two points. Used by the map
 * popup's "Get Directions" action — opens Maps with the route pre-filled so
 * tenants can get turn-by-turn directions + live ETA without leaving the app.
 * Coordinates are rounded to 6 decimals (~0.1 m) to keep the URL short.
 */
export function directionsUrl(
  destination: { lat: number; lng: number },
  origin?: { lat: number; lng: number } | null,
  mode: TravelMode = "walking"
): string {
  const point = (p: { lat: number; lng: number }) => `${p.lat.toFixed(6)},${p.lng.toFixed(6)}`;
  const dest = `destination=${point(destination)}`;
  const orig = origin ? `&origin=${point(origin)}` : "";
  return `https://www.google.com/maps/dir/?api=1${orig}&${dest}&travelmode=${mode}`;
}

/**
 * Approximate isochrone circle: a GeoJSON polygon approximating the set of
 * points reachable within `radiusKm` of a centre by walking (straight-line
 * distance scaled by the walking speed — no routing available offline).
 * Used for the map's travel-time overlay bands.
 */
export function walkingIsochrone(
  centre: { lat: number; lng: number },
  radiusKm: number,
  steps = 48
): GeoJSON.Feature<GeoJSON.Polygon> {
  const ring: [number, number][] = [];
  for (let i = 0; i < steps; i++) {
    const theta = (i / steps) * 2 * Math.PI;
    const dx = (radiusKm * Math.cos(theta)) / (111.32 * Math.cos((centre.lat * Math.PI) / 180));
    const dy = radiusKm / 110.574;
    ring.push([centre.lng + dx, centre.lat + dy]);
  }
  // Close the ring.
  ring.push(ring[0]);
  return {
    type: "Feature",
    geometry: { type: "Polygon", coordinates: [ring] },
    properties: { radiusKm },
  };
}

/**
 * Walking isochrones for the map's travel overlay — concentric bands at
 * 10/20/30 min walking, each with a colour for its travel-time band.
 */
export function travelIsochrones(centre: { lat: number; lng: number }): {
  feature: GeoJSON.Feature<GeoJSON.Polygon>;
  radiusKm: number;
  minutes: number;
  color: string;
}[] {
  return [
    { minutes: 10, color: "#22c55e" },
    { minutes: 20, color: "#f59e0b" },
    { minutes: 30, color: "#ef4444" },
  ].map((band) => {
    const radiusKm = (band.minutes / 60) * WALKING_SPEED_KMH;
    return {
      feature: walkingIsochrone(centre, radiusKm),
      radiusKm,
      minutes: band.minutes,
      color: band.color,
    };
  });
}
