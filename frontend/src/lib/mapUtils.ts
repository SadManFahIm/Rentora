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
