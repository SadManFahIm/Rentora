import { describe, expect, it } from "vitest";
import type { Room } from "../types";
import {
  avgPrice,
  buildBbox,
  landmarkToFeature,
  markerClassName,
  markerPrice,
  roomToFeature,
  roomsToFeatureCollection,
  shouldCluster,
  sortRoomsForList,
  tierColor,
  viewSummary,
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
