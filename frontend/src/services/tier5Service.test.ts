import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";
import { tier5Service } from "./tier5Service";

vi.mock("./api", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

const mockedGet = vi.mocked(api.get);
const mockedPost = vi.mocked(api.post);

describe("tier5Service", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("fetches a price recommendation for a room", async () => {
    const payload = {
      room_id: 3,
      current_price: 14000,
      suggested_price: 15000,
      direction: "raise",
      confidence: "medium",
      reasons: ["Area demand is rising (72/100) — active tenants in Dhanmondi."],
      signals: {
        area_demand_index: 72,
        area_demand_direction: "rising",
        market_position: "below_market",
        interest_30d: { bookings_30d: 2, wishlist_30d: 1, total: 3 },
      },
      note: "A suggestion from area demand + market + listing signals.",
    } as const;
    mockedGet.mockResolvedValue({ data: payload } as never);

    const result = await tier5Service.priceRecommendation(3);
    expect(mockedGet).toHaveBeenCalledWith("/rooms/3/price-recommendation/");
    expect(result.direction).toBe("raise");
    expect(result.reasons.length).toBeGreaterThan(0);
  });

  it("drafts a listing description from the form fields", async () => {
    const payload = {
      title: "Studio in Dhanmondi",
      description: "Available: a studio in Dhanmondi. ৳14,000/month.",
      amenities: ["wifi", "ac"],
      note: "Auto-drafted from your listing details — review and edit before publishing.",
    };
    mockedPost.mockResolvedValue({ data: payload } as never);

    const result = await tier5Service.generateDescription({
      area: "Dhanmondi",
      room_type: "studio",
      price: 14000,
      amenities: ["wifi"],
    });
    expect(mockedPost).toHaveBeenCalledWith("/rooms/generate-description/", {
      area: "Dhanmondi",
      room_type: "studio",
      price: 14000,
      amenities: ["wifi"],
    });
    expect(result.description).toContain("Dhanmondi");
  });
});
