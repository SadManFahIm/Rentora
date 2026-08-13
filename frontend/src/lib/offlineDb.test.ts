import { describe, it, expect, vi, beforeEach } from "vitest";
import { ROOMS_TTL_MS, buildCacheKey, cacheFresh, filterCachedRooms } from "./offlineDb";
import type { Room } from "../types";

const room = (overrides: Partial<Room> = {}): Room => ({
  id: 1,
  name: "Generic Room",
  type: "Studio",
  price: 12000,
  area: "Mirpur",
  lat: 23.74,
  lng: 90.38,
  rating: 4.5,
  reviews: 12,
  img: "/rooms/1.jpg",
  amenities: ["wifi", "furnished"],
  gender: "Any",
  available: true,
  featured: false,
  tier: "free",
  tierExpiresAt: null,
  description: "Basic furnished room",
  size: 300,
  owner: "Owner",
  ownerId: 1,
  ownerAvatar: "",
  verified: false,
  ...overrides,
});

describe("buildCacheKey", () => {
  it("is stable regardless of object key order", () => {
    expect(buildCacheKey({ a: "1", b: "2" })).toBe(buildCacheKey({ b: "2", a: "1" }));
  });

  it("encodes query param pairs", () => {
    expect(buildCacheKey({ q: "uttara", price__lte: "15000" })).toBe("price__lte=15000&q=uttara");
  });
});

describe("cacheFresh", () => {
  it("respects the TTL window", () => {
    const ts = 1_000_000;
    expect(cacheFresh(ts, ROOMS_TTL_MS, ts + ROOMS_TTL_MS - 1)).toBe(true);
    expect(cacheFresh(ts, ROOMS_TTL_MS, ts + ROOMS_TTL_MS + 1)).toBe(false);
  });
});

describe("filterCachedRooms", () => {
  const rooms = [
    room({
      id: 1,
      price: 8000,
      area: "Uttara",
      name: "Single in Uttara",
      type: "Single",
      verified: true,
    }),
    room({
      id: 2,
      price: 12000,
      area: "Dhanmondi",
      name: "Studio in Dhanmondi",
      type: "Studio",
      verified: false,
    }),
    room({
      id: 3,
      price: 20000,
      area: "Gulshan",
      name: "Studio in Gulshan",
      type: "Studio",
      available: false,
    }),
  ];

  beforeEach(() => vi.restoreAllMocks());

  it("filters by text query across name/description/area", () => {
    const out = filterCachedRooms(rooms, { query: "dhanmondi" });
    expect(out.map((r) => r.id)).toEqual([2]);
  });

  it("filters by budget range", () => {
    const out = filterCachedRooms(rooms, { minPrice: "9000", maxPrice: "15000" });
    expect(out.map((r) => r.id)).toEqual([2]);
  });

  it("combines area + type + verified", () => {
    const out = filterCachedRooms(rooms, { area: "Uttara", type: "single", verified: true });
    expect(out.map((r) => r.id)).toEqual([1]);
  });

  it("filters by amenities (all required)", () => {
    const out = filterCachedRooms(rooms, { amenities: ["wifi", "furnished"] });
    expect(out.map((r) => r.id)).toEqual([1, 2, 3]);
  });

  it("honors availability", () => {
    const out = filterCachedRooms(rooms, { available: "yes" });
    expect(out.map((r) => r.id)).toEqual([1, 2]);
  });

  it("sorts by price ascending and descending", () => {
    const asc = filterCachedRooms(rooms, { sort: "price-asc" });
    expect(asc.map((r) => r.price)).toEqual([8000, 12000, 20000]);
    const desc = filterCachedRooms(rooms, { sort: "price-desc" });
    expect(desc.map((r) => r.price)).toEqual([20000, 12000, 8000]);
  });

  it("does not mutate the input array", () => {
    const snapshot = rooms.map((r) => r.id);
    filterCachedRooms(rooms, { sort: "price-desc" });
    expect(rooms.map((r) => r.id)).toEqual(snapshot);
  });
});
