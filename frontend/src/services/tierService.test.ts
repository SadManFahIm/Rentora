import { describe, expect, it, vi, beforeEach } from "vitest";
import { mapRoom } from "./mappers";

vi.mock("./api", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

import { api } from "./api";
import { paymentService } from "./paymentService";
import { roomService } from "./roomService";

function apiRoom(overrides: Record<string, unknown> = {}) {
  return {
    id: 7,
    title: "Premium Studio",
    description: "test",
    room_type: "studio",
    price: "15000.00",
    area: "Banani",
    lat: "23.79",
    lng: "90.41",
    amenities: ["wifi"],
    gender_preference: "any",
    size_sqft: 420,
    is_available: true,
    tier: "free",
    tier_expires_at: null,
    is_featured: false,
    rating: "4.6",
    total_reviews: 15,
    verified: false,
    created_at: "2025-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("mapRoom tier mapping", () => {
  it("defaults missing tier to free", () => {
    const { tier, featured } = mapRoom(apiRoom({ tier: undefined }));
    expect(tier).toBe("free");
    expect(featured).toBe(false);
  });

  it("maps featured tier + keeps is_featured derived", () => {
    const room = mapRoom(apiRoom({ tier: "featured", is_featured: false }));
    expect(room.tier).toBe("featured");
    expect(room.featured).toBe(true); // derived from tier, not raw flag
  });

  it("maps premium tier and expiry", () => {
    const expires = "2026-09-01T00:00:00Z";
    const room = mapRoom(apiRoom({ tier: "premium", tier_expires_at: expires }));
    expect(room.tier).toBe("premium");
    expect(room.tierExpiresAt).toBe(expires);
    expect(room.featured).toBe(true);
  });
});

describe("roomService.getTierCatalog", () => {
  beforeEach(() => vi.clearAllMocks());

  it("maps the snake_case catalog to camelCase", async () => {
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: {
        tiers: [
          { tier: "free", label: "Free", price: 0, benefits: ["Standard placement"] },
          { tier: "featured", label: "Featured", price: 199, benefits: ["Boosted"] },
          { tier: "premium", label: "Premium", price: 499, benefits: ["Top of search"] },
        ],
        duration_days: 30,
        currency: "BDT",
      },
    });
    const catalog = await roomService.getTierCatalog();
    expect(api.get).toHaveBeenCalledWith("/rooms/tier-catalog/");
    expect(catalog.durationDays).toBe(30);
    expect(catalog.tiers).toHaveLength(3);
    expect(catalog.tiers[1].price).toBe(199);
    expect(catalog.tiers[2].tier).toBe("premium");
  });
});

describe("roomService owner filter", () => {
  beforeEach(() => vi.clearAllMocks());

  it("passes owner param when set", async () => {
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { count: 1, next: null, previous: null, results: [apiRoom()] },
    });
    await roomService.getRooms({ owner: 3 });
    expect(api.get).toHaveBeenCalledWith("/rooms/", {
      params: expect.objectContaining({ owner: "3" }),
    });
  });
});

describe("paymentService.initiateTierUpgrade", () => {
  beforeEach(() => vi.clearAllMocks());

  it("posts room + tier + method to the tier-upgrade endpoint", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { payment_url: "https://gw.example/pay", transaction_id: "abc123" },
    });
    const result = await paymentService.initiateTierUpgrade(7, "premium", "bkash");
    expect(api.post).toHaveBeenCalledWith("/payments/tier-upgrade/initiate/", {
      room_id: 7,
      tier: "premium",
      method: "bkash",
    });
    expect(result.paymentUrl).toBe("https://gw.example/pay");
    expect(result.transactionId).toBe("abc123");
  });

  it("falls back to bkash_url when present", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { bkash_url: "https://gw.example/bkash", transaction_id: "abc123" },
    });
    const result = await paymentService.initiateTierUpgrade(7, "featured", "bkash");
    expect(result.paymentUrl).toBe("https://gw.example/bkash");
  });
});
