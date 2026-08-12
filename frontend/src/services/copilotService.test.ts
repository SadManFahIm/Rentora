import { describe, expect, it, vi, beforeEach } from "vitest";

vi.mock("./api", () => ({
  default: {
    post: vi.fn(),
  },
}));

import api from "./api";
import { sendCopilotMessage } from "./copilotService";

const apiResponse = {
  session_id: "abc123",
  message: "I found 2 matching rooms in Uttara · under ৳10,000.",
  intent: {
    budget_max: 10000,
    areas: ["Uttara"],
    room_type: null,
    gender: null,
    months: [],
    amenities: ["Furnished"],
    property_words: [],
    hints: ["Budget ≤ ৳10,000", "Uttara", "Furnished"],
  },
  listings: [
    {
      id: 29,
      title: "Student Room, Uttara Sector 10",
      price: 8500,
      area: "Uttara",
      room_type: "single",
      amenities: ["WiFi", "Furnished"],
      verified: true,
      tier: "free",
      image: null,
    },
  ],
  total_count: 2,
  suggestions: ["দাম অনুযায়ী সাজাও"],
};

describe("copilotService", () => {
  beforeEach(() => vi.clearAllMocks());

  it("sends a message and returns the structured reply", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: apiResponse });
    const res = await sendCopilotMessage("Uttara-তে ১০ হাজারের মধ্যে furnished room", null);
    expect(res.session_id).toBe("abc123");
    expect(res.listings).toHaveLength(1);
    expect(res.listings[0].price).toBe(8500);
    expect(res.intent.areas).toEqual(["Uttara"]);
    expect(api.post).toHaveBeenCalledWith("/copilot/chat/", {
      message: "Uttara-তে ১০ হাজারের মধ্যে furnished room",
    });
  });

  it("echoes the session id for follow-up context", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: apiResponse });
    await sendCopilotMessage("শুধু furnished দেখাও", "abc123");
    expect(api.post).toHaveBeenCalledWith("/copilot/chat/", {
      message: "শুধু furnished দেখাও",
      session_id: "abc123",
    });
  });

  it("never fabricates: listings come from the API as-is", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: apiResponse });
    const res = await sendCopilotMessage("anything", null);
    expect(res.total_count).toBe(2);
    expect(res.listings.length).toBeLessThanOrEqual(res.total_count);
  });
});
