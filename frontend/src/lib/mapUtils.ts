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
