import { describe, expect, it, vi, beforeEach } from "vitest";

vi.mock("./api", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

import { api } from "./api";
import { roomService } from "./roomService";

const apiRoom = (overrides: Record<string, unknown> = {}) => ({
  id: 7,
  title: "Sunlit Studio, Dhanmondi",
  description: "test",
  room_type: "studio",
  price: "12000.00",
  area: "Dhanmondi",
  lat: "23.7461",
  lng: "90.3742",
  amenities: ["WiFi", "AC"],
  gender_preference: "any",
  size_sqft: 450,
  is_available: true,
  tier: "free",
  tier_expires_at: null,
  is_featured: false,
  rating: "4.8",
  total_reviews: 24,
  verified: true,
  created_at: "2025-01-01T00:00:00Z",
  ...overrides,
});

describe("roomService.getRooms params", () => {
  beforeEach(() => vi.clearAllMocks());

  const respond = (rooms: unknown[] = [apiRoom()]) =>
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { count: rooms.length, next: null, previous: null, results: rooms },
    });

  it("maps the full filter set into backend query params", async () => {
    respond();
    await roomService.getRooms({
      query: "studio",
      area: "Banani",
      type: "studio",
      gender: "Female",
      minPrice: "8000",
      maxPrice: "15000",
      available: "yes",
      sort: "price-asc",
      owner: 3,
    });
    expect(api.get).toHaveBeenCalledWith("/rooms/", {
      params: {
        q: "studio",
        area: "Banani",
        room_type: "studio",
        gender_preference: "female",
        price__gte: "8000",
        price__lte: "15000",
        is_available: "true",
        ordering: "price",
        owner: "3",
      },
    });
  });

  it("omits default values and maps sort variants", async () => {
    respond();
    await roomService.getRooms({ area: "All", type: "All", gender: "Any", sort: "price-desc" });
    expect(api.get).toHaveBeenCalledWith("/rooms/", {
      params: { ordering: "-price" },
    });
    respond();
    await roomService.getRooms({ sort: "rating" });
    expect(api.get).toHaveBeenCalledWith("/rooms/", {
      params: { ordering: "-rating" },
    });
    respond();
    await roomService.getRooms({});
    expect(api.get).toHaveBeenCalledWith("/rooms/", { params: {} });
  });

  it("filters amenities client-side", async () => {
    const withWifi = apiRoom({ id: 1, amenities: ["WiFi", "AC"] });
    const noWifi = apiRoom({ id: 2, amenities: ["AC"] });
    respond([withWifi, noWifi]);
    const rooms = await roomService.getRooms({ amenities: ["WiFi"] });
    expect(rooms.map((r) => r.id)).toEqual([1]);
  });
});

describe("roomService.getRoomById", () => {
  it("fetches and maps a single room", async () => {
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: apiRoom() });
    const room = await roomService.getRoomById(7);
    expect(api.get).toHaveBeenCalledWith("/rooms/7/");
    expect(room.id).toBe(7);
    expect(room.name).toBe("Sunlit Studio, Dhanmondi");
  });
});

describe("roomService.createRoom", () => {
  it("posts the snake_case payload and maps the response", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: apiRoom() });
    const room = await roomService.createRoom({
      name: "Sunlit Studio, Dhanmondi",
      description: "test",
      type: "Studio",
      price: 12000,
      area: "Dhanmondi",
      lat: 23.7461,
      lng: 90.3742,
      amenities: ["WiFi"],
      gender: "Any",
      size: 450,
      available: true,
      featured: false,
      img: "https://img.example/x.jpg",
      tier: "free",
      tierExpiresAt: null,
      owner: "Rahim Hossain",
      ownerId: 3,
      ownerAvatar: "RH",
      verified: true,
    });
    expect(api.post).toHaveBeenCalledWith("/rooms/", {
      title: "Sunlit Studio, Dhanmondi",
      description: "test",
      room_type: "studio",
      price: 12000,
      area: "Dhanmondi",
      address: "Dhanmondi, Dhaka",
      lat: 23.7461,
      lng: 90.3742,
      amenities: ["WiFi"],
      gender_preference: "any",
      size_sqft: 450,
      is_available: true,
    });
    expect(room.id).toBe(7);
  });
});

describe("roomService smart search", () => {
  beforeEach(() => vi.clearAllMocks());

  it("sends smart=1 with the q param and maps nl_parsed", async () => {
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: {
        count: 1,
        next: null,
        previous: null,
        results: [apiRoom()],
        nl_parsed: {
          budget_max: 10000,
          areas: ["Uttara"],
          room_type: null,
          gender: null,
          months: ["July"],
          hints: ["Budget ≤ ৳10,000", "Uttara", "move-in July"],
        },
      },
    });

    const result = await roomService.searchRoomsSmart({ query: "১০ হাজার uttara" });

    expect(api.get).toHaveBeenCalledWith("/rooms/", {
      params: { q: "১০ হাজার uttara", smart: "1" },
    });
    expect(result.rooms).toHaveLength(1);
    expect(result.rooms[0].name).toBe("Sunlit Studio, Dhanmondi");
    expect(result.nlParsed?.budget_max).toBe(10000);
    expect(result.nlParsed?.hints).toContain("Uttara");
  });

  it("returns nlParsed null when the backend sends none", async () => {
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { count: 0, next: null, previous: null, results: [] },
    });
    const result = await roomService.searchRoomsSmart({ query: "x" });
    expect(result.nlParsed).toBeNull();
    expect(result.rooms).toHaveLength(0);
  });
});

describe("roomService image similarity", () => {
  beforeEach(() => vi.clearAllMocks());

  it("fetches similar images for a room and maps phash_distance", async () => {
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: [{ ...apiRoom(), id: 8, phash_distance: 2 }],
    });
    const matches = await roomService.getSimilarImages(7);
    expect(api.get).toHaveBeenCalledWith("/rooms/7/similar-images/", {
      params: { limit: 4 },
    });
    expect(matches[0].id).toBe(8);
    expect(matches[0].phash_distance).toBe(2);
  });
});
