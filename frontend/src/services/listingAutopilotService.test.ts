import { describe, expect, it, vi, beforeEach } from "vitest";

vi.mock("./api", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

import { api } from "./api";
import {
  approveAutopilotProposal,
  bulkApproveAutopilotProposals,
  getAutopilotOverview,
  listAutopilotAnalyses,
  listAutopilotProposals,
  rejectAutopilotProposal,
} from "./listingAutopilotService";

describe("listingAutopilotService", () => {
  beforeEach(() => vi.clearAllMocks());

  it("fetches overview + proposals + analyses", async () => {
    (api.get as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({
        data: { enabled: true, pending_count: 3, agent: "ai.listing_autopilot" },
      })
      .mockResolvedValueOnce({
        data: {
          proposals: [
            {
              key: "prop-1",
              type: "PRICE_UPDATE",
              status: "pending",
              title: "Price — Listing #1",
              summary: "Price suggestion: raise to ৳12,000",
              room_id: 1,
              grounding_key: "abc",
              recommendation: {},
              arguments: { new_price: 12000 },
              created_at: null,
              expires_at: null,
              reviewed_at: null,
              applied_at: null,
              application_result: null,
              rejection_reason: null,
              conversation_id: null,
            },
          ],
        },
      })
      .mockResolvedValueOnce({
        data: {
          analyses: [
            {
              id: 7,
              room_id: 1,
              week_key: "2026-W35",
              eligible: true,
              quality_score: 72,
              property_score: null,
              property_confidence: "",
              price_direction: "raise",
              suggested_price: 12000,
              stale_days: 3,
              summary: "ok",
              created_at: null,
            },
          ],
        },
      });

    const overview = await getAutopilotOverview();
    expect(overview.pending_count).toBe(3);
    expect(api.get).toHaveBeenCalledWith("/autopilot/overview/");

    const proposals = await listAutopilotProposals("pending");
    expect(proposals.proposals[0].type).toBe("PRICE_UPDATE");
    expect(api.get).toHaveBeenCalledWith("/autopilot/proposals/", {
      params: { status: "pending" },
    });

    const analyses = await listAutopilotAnalyses();
    expect(analyses.analyses[0].week_key).toBe("2026-W35");
    expect(api.get).toHaveBeenCalledWith("/autopilot/analyses/");
  });

  it("list proposals without a status filter omits the query param", async () => {
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: { proposals: [] } });
    await listAutopilotProposals("");
    expect(api.get).toHaveBeenCalledWith("/autopilot/proposals/", { params: undefined });
  });

  it("approve posts to the per-proposal approve endpoint", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { proposal_key: "prop-1", status: "applied" },
    });
    const res = await approveAutopilotProposal("prop-1");
    expect(res.status).toBe("applied");
    expect(api.post).toHaveBeenCalledWith("/autopilot/proposals/prop-1/approve/");
  });

  it("reject posts the optional reason", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { proposal_key: "prop-1", status: "rejected" },
    });
    const res = await rejectAutopilotProposal("prop-1", "no thank you");
    expect(res.status).toBe("rejected");
    expect(api.post).toHaveBeenCalledWith("/autopilot/proposals/prop-1/reject/", {
      reason: "no thank you",
    });
  });

  it("bulk approve posts the selected proposal keys", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { applied: [{ key: "a", status: "applied" }], skipped: [] },
    });
    const res = await bulkApproveAutopilotProposals(["a", "b"]);
    expect(res.applied).toHaveLength(1);
    expect(res.skipped).toHaveLength(0);
    expect(api.post).toHaveBeenCalledWith("/autopilot/proposals/bulk-approve/", {
      proposal_keys: ["a", "b"],
    });
  });
});
