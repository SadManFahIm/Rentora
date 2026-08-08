import { describe, expect, it } from "vitest";
import type { Room } from "../types";
import {
  avgPrice,
  buildBbox,
  directionsUrl,
  drivingMinutes,
  formatDistance,
  formatDriveTime,
  formatTravelTime,
  haversineKm,
  landmarkToFeature,
  landmarksToFeatureCollection,
  markerClassName,
  markerPrice,
  metroRouteFeatureCollection,
  quantizeBounds,
  roomToFeature,
  roomsToFeatureCollection,
  shouldCluster,
  sortRoomsForList,
  tierColor,
  travelIsochrones,
  viewSummary,
  walkingIsochrone,
  walkingMinutes,
} from "./mapUtils";

function makeRoom(overrides: Partial<Room> = {}): Room {
  return {
    id: 1,
    name: "Sunny Studio",
    type: "Studio",
    price: 12000,
    area: "Dhanmondi",
    lat: 23.746,
    lng: 90.376,
    rating: 4.5,
    reviews: 12,
    img: "",
    amenities: [],
    gender: "Any",
    available: true,
    featured: false,
    tier: "free",
    tierExpiresAt: null,
    description: "",
    size: 300,
    owner: "Rahim",
    ownerId: 2,
    ownerAvatar: "R",
    verified: false,
    ...overrides,
  };
}

describe("buildBbox", () => {
  it("produces GeoJSON-order minLng,minLat,maxLng,maxLat", () => {
    expect(buildBbox({ west: 90.3, south: 23.7, east: 90.5, north: 23.9 })).toBe(
      "90.300000,23.700000,90.500000,23.900000"
    );
  });

  it("clamps non-finite values to 0", () => {
    expect(buildBbox({ west: NaN, south: 23.7, east: 90.5, north: Infinity })).toBe(
      "0.000000,23.700000,90.500000,0.000000"
    );
  });
});

describe("roomToFeature / roomsToFeatureCollection", () => {
  it("converts a room to a point feature with lng/lat ordering", () => {
    const room = makeRoom();
    const feature = roomToFeature(room);
    expect(feature.geometry.type).toBe("Point");
    const coords = feature.geometry as GeoJSON.Point;
    expect(coords.coordinates).toEqual([90.376, 23.746]);
    expect(feature.properties?.id).toBe(1);
    expect(feature.properties?.price).toBe(12000);
    expect(feature.properties?.tier).toBe("free");
  });

  it("wraps multiple rooms in a FeatureCollection", () => {
    const fc = roomsToFeatureCollection([makeRoom(), makeRoom({ id: 2 })]);
    expect(fc.type).toBe("FeatureCollection");
    expect(fc.features).toHaveLength(2);
  });
});

describe("landmarkToFeature", () => {
  it("maps kind into properties for layer styling", () => {
    const f = landmarkToFeature({
      key: "du",
      name: "DU",
      kind: "university",
      lat: 23.73,
      lng: 90.39,
    });
    const coords = f.geometry as GeoJSON.Point;
    expect(coords.coordinates).toEqual([90.39, 23.73]);
    expect(f.properties?.kind).toBe("university");
  });
});

describe("tierColor / markerClassName", () => {
  it("returns distinct colors per tier", () => {
    expect(tierColor("free")).toBe("#ea580c");
    expect(tierColor("featured")).toBe("#3b82f6");
    expect(tierColor("premium")).toBe("#f59e0b");
  });

  it("returns a class that carries the tier modifier", () => {
    expect(markerClassName("free")).toBe("map-marker");
    expect(markerClassName("featured")).toBe("map-marker map-marker--featured");
    expect(markerClassName("premium")).toContain("map-marker--premium");
  });
});

describe("markerPrice", () => {
  it("compacts thousands to k-notation", () => {
    expect(markerPrice(12000)).toBe("৳12k");
    expect(markerPrice(500)).toBe("৳500");
    expect(markerPrice(199000)).toBe("৳199k");
  });
});

describe("avgPrice", () => {
  it("returns null for an empty list", () => {
    expect(avgPrice([])).toBeNull();
  });

  it("rounds the mean", () => {
    expect(avgPrice([makeRoom({ price: 10000 }), makeRoom({ price: 15000 })])).toBe(12500);
  });
});

describe("shouldCluster", () => {
  it("keeps individual pins for small lists", () => {
    expect(shouldCluster(5)).toBe(false);
  });

  it("clusters once listings grow past the threshold", () => {
    expect(shouldCluster(12)).toBe(true);
    expect(shouldCluster(40, 30)).toBe(true);
  });
});

describe("sortRoomsForList", () => {
  it("orders premium > featured > free, then price ascending", () => {
    const rooms = [
      makeRoom({ id: 1, tier: "free", price: 8000 }),
      makeRoom({ id: 2, tier: "premium", price: 20000 }),
      makeRoom({ id: 3, tier: "featured", price: 15000 }),
    ];
    expect(sortRoomsForList(rooms).map((r) => r.id)).toEqual([2, 3, 1]);
  });

  it("pushes unavailable rooms to the end", () => {
    const rooms = [
      makeRoom({ id: 1, available: false, price: 5000 }),
      makeRoom({ id: 2, available: true, price: 9000 }),
    ];
    expect(sortRoomsForList(rooms).map((r) => r.id)).toEqual([2, 1]);
  });

  it("does not mutate the input", () => {
    const rooms = [makeRoom({ id: 2 }), makeRoom({ id: 1 })];
    sortRoomsForList(rooms);
    expect(rooms.map((r) => r.id)).toEqual([2, 1]);
  });
});

describe("quantizeBounds", () => {
  it("rounds outward so the box never shrinks below the visible area", () => {
    const q = quantizeBounds({
      west: 90.37655,
      south: 23.74255,
      east: 90.37745,
      north: 23.74345,
    });
    // Floor on min, ceil on max — never tighter than the input.
    expect(q.west).toBe(90.376);
    expect(q.south).toBe(23.742);
    expect(q.east).toBe(90.378);
    expect(q.north).toBe(23.744);
  });
});

describe("haversineKm", () => {
  it("returns 0 for identical points", () => {
    expect(haversineKm(23.746, 90.376, 23.746, 90.376)).toBe(0);
  });

  it("computes a plausible Dhaka-scale distance (~1.2 km in Dhanmondi)", () => {
    // Roughly a km of north–south distance in Dhaka.
    const km = haversineKm(23.746, 90.376, 23.756, 90.376);
    expect(km).toBeGreaterThan(1.0);
    expect(km).toBeLessThan(1.3);
  });
});

describe("walkingMinutes / formatTravelTime", () => {
  it("estimates walking time from distance at ~4.5 km/h", () => {
    // 1 km at 4.5 km/h = ~13.3 min.
    expect(walkingMinutes(1)).toBe(13);
    expect(walkingMinutes(0)).toBe(0);
  });

  it("formats a human travel-time label", () => {
    expect(formatTravelTime(0.3)).toBe("≈ 4 min walk");
    expect(formatTravelTime(0.02)).toBe("< 1 min walk");
  });
});

describe("formatDistance", () => {
  it("shows metres under 1 km and km above", () => {
    expect(formatDistance(0.85)).toBe("850 m");
    expect(formatDistance(1.2)).toBe("1.2 km");
  });
});

describe("drivingMinutes / formatDriveTime", () => {
  it("estimates driving time at the conservative urban speed", () => {
    // 3 km at 18 km/h = 10 min.
    expect(drivingMinutes(3)).toBe(10);
    expect(drivingMinutes(0)).toBe(0);
  });

  it("formats a human drive-time label", () => {
    expect(formatDriveTime(3)).toBe("≈ 10 min drive");
    expect(formatDriveTime(0.1)).toBe("< 1 min drive");
  });
});

describe("directionsUrl", () => {
  it("builds a Google Maps walking-route link to the destination", () => {
    const url = directionsUrl({ lat: 23.746, lng: 90.376 });
    expect(url).toContain("google.com/maps/dir");
    expect(url).toContain("destination=23.746000,90.376000");
    expect(url).toContain("travelmode=walking");
    expect(url).not.toContain("origin=");
  });

  it("includes the origin when a search point is active", () => {
    const url = directionsUrl({ lat: 23.746, lng: 90.376 }, { lat: 23.75, lng: 90.37 });
    expect(url).toContain("origin=23.750000,90.370000");
  });

  it("rounds full-precision coordinates to keep the URL short", () => {
    const url = directionsUrl({ lat: 23.792611111, lng: 90.416722222 });
    expect(url).toContain("destination=23.792611,90.416722");
    expect(url).not.toContain(".2222");
  });

  it("defaults to walking and accepts driving/transit modes", () => {
    const dest = { lat: 23.746, lng: 90.376 };
    expect(directionsUrl(dest)).toContain("travelmode=walking");
    expect(directionsUrl(dest, null, "driving")).toContain("travelmode=driving");
    expect(directionsUrl(dest, null, "transit")).toContain("travelmode=transit");
  });
});

describe("walkingIsochrone", () => {
  it("builds a closed polygon with the requested radius", () => {
    const ring = walkingIsochrone({ lat: 23.746, lng: 90.376 }, 1).geometry.coordinates[0];
    expect(ring.length).toBe(49); // 48 segments + closure
    const first = ring[0];
    expect(first).toEqual(ring[ring.length - 1]); // closed
    // East-west half-width ~1 km at Dhaka latitude.
    expect(Math.abs(ring[12][0] - first[0])).toBeGreaterThan(0.008);
  });
});

describe("metroRouteFeatureCollection", () => {
  const stations = [
    { key: "mrt_motijheel", name: "Motijheel", kind: "metro" as const, lat: 23.727, lng: 90.418 },
    {
      key: "mrt_uttara_north",
      name: "Uttara North",
      kind: "metro" as const,
      lat: 23.869,
      lng: 90.369,
    },
    { key: "mrt_shahbagh", name: "Shahbagh", kind: "metro" as const, lat: 23.739, lng: 90.396 },
  ];

  it("threads stations north-to-south in one LineString", () => {
    const fc = metroRouteFeatureCollection(stations);
    const line = fc.features[0] as GeoJSON.Feature<GeoJSON.LineString>;
    const coords = line.geometry.coordinates;
    expect(coords[0]).toEqual([90.369, 23.869]); // Uttara North first (northernmost)
    expect(coords[2]).toEqual([90.418, 23.727]); // Motijheel last (southernmost)
  });

  it("returns no features with fewer than two stations", () => {
    const fc = metroRouteFeatureCollection([stations[0]]);
    expect(fc.features).toHaveLength(0);
  });

  it("leaves landmarksToFeatureCollection intact for point layers", () => {
    const fc = landmarksToFeatureCollection(stations);
    expect(fc.features).toHaveLength(3);
  });
});

describe("travelIsochrones", () => {
  it("returns three bands at 10/20/30 min with growing radii", () => {
    const bands = travelIsochrones({ lat: 23.746, lng: 90.376 });
    expect(bands.map((b) => b.minutes)).toEqual([10, 20, 30]);
    const radii = bands.map((b) => b.radiusKm);
    expect(radii[0]).toBeLessThan(radii[1]);
    expect(radii[1]).toBeLessThan(radii[2]);
  });
});

describe("viewSummary", () => {
  it("handles the empty state", () => {
    expect(viewSummary([])).toBe("No rooms in view");
  });

  it("counts available vs total", () => {
    expect(viewSummary([makeRoom({ available: true }), makeRoom({ available: false })])).toBe(
      "1 of 2 rooms available"
    );
  });

  it("handles the singular", () => {
    expect(viewSummary([makeRoom()])).toBe("1 of 1 room available");
  });
});
