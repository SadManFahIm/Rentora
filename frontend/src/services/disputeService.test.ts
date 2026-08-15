import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./api", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

import { api } from "./api";
import { disputeService } from "./disputeService";

const apiDispute = {
  id: 41,
  booking: 7,
  room_id: 3,
  room_title: "Sunlit Studio",
  opened_by: 5,
  opened_by_username: "sabbir.rahman",
  other_party_username: "rahim.hossain",
  category: "deposit",
  category_display: "Security deposit",
  description: "Deposit not returned after move-out.",
  status: "open",
  status_display: "Open",
  decision: "none",
  decision_display: "No decision",
  decision_amount: null,
  resolution: "",
  evidence: [
    {
      id: 9,
      dispute: 41,
      uploaded_by: 5,
      uploaded_by_username: "sabbir.rahman",
      kind: "text",
      kind_display: "Text statement",
      content: "Left the flat clean on the 1st.",
      file: null,
      created_at: "2026-01-05T10:00:00Z",
    },
  ],
  created_at: "2026-01-05T09:00:00Z",
  updated_at: "2026-01-05T10:00:00Z",
  resolved_at: null,
};

describe("disputeService (Phase 12)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("getDisputes maps the dispute with its evidence", async () => {
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: [apiDispute] });
    const disputes = await disputeService.getDisputes();
    expect(api.get).toHaveBeenCalledWith("/disputes/");
    expect(disputes[0]).toMatchObject({
      id: 41,
      booking: 7,
      roomId: 3,
      roomTitle: "Sunlit Studio",
      category: "deposit",
      categoryDisplay: "Security deposit",
      status: "open",
      statusDisplay: "Open",
      decision: "none",
    });
    expect(disputes[0].evidence).toHaveLength(1);
    expect(disputes[0].evidence[0].kindDisplay).toBe("Text statement");
  });

  it("createDispute posts the payload", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: apiDispute });
    await disputeService.createDispute({
      booking: 7,
      category: "deposit",
      description: "Deposit not returned.",
    });
    expect(api.post).toHaveBeenCalledWith("/disputes/", {
      booking: 7,
      category: "deposit",
      description: "Deposit not returned.",
    });
  });

  it("addEvidence posts to the evidence endpoint", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: apiDispute.evidence[0],
    });
    const evidence = await disputeService.addEvidence(41, { kind: "text", content: "Left clean." });
    expect(api.post).toHaveBeenCalledWith("/disputes/41/evidence/", {
      kind: "text",
      content: "Left clean.",
    });
    expect(evidence.uploadedByUsername).toBe("sabbir.rahman");
  });

  it("getAdminDisputes passes the status filter", async () => {
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: [apiDispute] });
    await disputeService.getAdminDisputes("open");
    expect(api.get).toHaveBeenCalledWith("/disputes/admin/", { params: { status: "open" } });
  });

  it("actOnDispute posts the admin decision", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: {
        ...apiDispute,
        status: "resolved",
        status_display: "Resolved",
        decision: "refund_to_tenant",
        decision_display: "Deposit refunded to tenant",
        resolution: "Deposit returned in full.",
      },
    });
    const dispute = await disputeService.actOnDispute(41, {
      action: "resolve",
      decision: "refund_to_tenant",
      decisionAmount: 5000,
      resolution: "Deposit returned in full.",
    });
    expect(api.post).toHaveBeenCalledWith("/disputes/admin/41/action/", {
      action: "resolve",
      decision: "refund_to_tenant",
      decisionAmount: 5000,
      resolution: "Deposit returned in full.",
    });
    expect(dispute.status).toBe("resolved");
    expect(dispute.decision).toBe("refund_to_tenant");
  });
});
