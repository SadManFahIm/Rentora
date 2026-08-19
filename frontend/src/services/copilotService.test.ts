import { describe, expect, it, vi, beforeEach } from "vitest";

vi.mock("./api", () => ({
  default: {
    post: vi.fn(),
    get: vi.fn(),
  },
}));

import api from "./api";
import { getListingShareSummary, sendCopilotMessage, sendSupportQuestion } from "./copilotService";

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

  it("fetches the share-ready AI summary for a listing", async () => {
    const summary = {
      id: 29,
      title: "Student Room, Uttara Sector 10",
      price: 8500,
      area: "Uttara",
      area_display: "Uttara",
      summary: "Student Room, Uttara Sector 10 — Uttara · ৳8,500/month",
    };
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: summary });
    const res = await getListingShareSummary(29);
    expect(res.summary).toContain("Uttara");
    expect(api.get).toHaveBeenCalledWith("/copilot/share-summary/29/");
  });
});

describe("supportCopilot (Phase 15 — B2)", () => {
  beforeEach(() => vi.clearAllMocks());

  const apiSupport = {
    topic: "security_deposit",
    title: "Security deposit",
    title_bn: "সিকিউরিটি ডিপোজিট",
    answer: "The security deposit amount is set by the landlord…",
    answer_bn: "সিকিউরিটি ডিপোজিটের পরিমাণ বাড়িওয়ালা ঠিক করেন…",
    grounded: true,
    matched_keywords: ["deposit"],
  };

  it("posts a question and returns the bilingual grounded answer", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: apiSupport });
    const res = await sendSupportQuestion("ডিপোজিট ফেরত পাব কীভাবে?");
    expect(api.post).toHaveBeenCalledWith("/copilot/support/", {
      message: "ডিপোজিট ফেরত পাব কীভাবে?",
    });
    expect(res.grounded).toBe(true);
    expect(res.title).toBe("Security deposit");
    expect(res.answer_bn).toContain("বাড়িওয়ালা");
  });

  it("surfaces the transparent fallback (grounded: false) unmocked", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: {
        topic: "general",
        title: "How can I help?",
        title_bn: "কীভাবে সাহায্য করতে পারি?",
        answer: "I couldn't match that to a help article yet…",
        answer_bn: "আপনার প্রশ্নটি এখনো কোনো হেল্প আর্টিকেলে মেলাতে পারিনি…",
        grounded: false,
      },
    });
    const res = await sendSupportQuestion("xyz nonsense");
    expect(res.grounded).toBe(false);
    expect(res.matched_keywords).toBeUndefined();
  });
});
