import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./api", () => ({
  api: {
    post: vi.fn(),
    get: vi.fn(),
  },
}));

import { api } from "./api";
import {
  approveNegotiationProposal,
  cancelNegotiation,
  getNegotiation,
  getNegotiationConversation,
  getNegotiationRun,
  listNegotiations,
  rejectNegotiation,
  rejectNegotiationOffer,
  rejectNegotiationProposal,
  sendNegotiationTurn,
} from "./negotiationAgentService";

const turnResponse = {
  conversation_id: 7,
  run_key: "11111111-1111-1111-1111-111111111111",
  status: "pending",
  task_id: "task-1",
};

const negotiationRow = {
  key: "n-key-1",
  room_id: 29,
  room_title: "Student Room, Uttara Sector 10",
  room_price: 8500,
  status: "active",
  my_role: "tenant",
  peer_name: "Sadman",
  updated_at: "2026-09-01T10:00:00Z",
  last_offer: { amount: 8000, status: "sent", kind: "offer", created_at: "2026-09-01T09:00:00Z" },
};

describe("negotiationAgentService (Phase 19.4)", () => {
  beforeEach(() => vi.clearAllMocks());

  it("starts a new negotiation chat bound to a room", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: turnResponse });
    const res = await sendNegotiationTurn("Can I ask for a lower rent?", { roomId: 29 });
    expect(res.run_key).toBe(turnResponse.run_key);
    expect(api.post).toHaveBeenCalledWith("/negotiation/chat/", {
      message: "Can I ask for a lower rent?",
      room_id: 29,
    });
  });

  it("continues an existing conversation via conversation_id (no room_id)", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: turnResponse });
    await sendNegotiationTurn("Counter that please", { conversationId: 7 });
    expect(api.post).toHaveBeenCalledWith("/negotiation/chat/", {
      message: "Counter that please",
      conversation_id: 7,
    });
  });

  it("polls a run from the caller's own negotiations endpoint", async () => {
    const run = { ...turnResponse, status: "completed", total_tokens: 120 };
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: run });
    const res = await getNegotiationRun(turnResponse.run_key);
    expect(res.status).toBe("completed");
    expect(res.total_tokens).toBe(120);
    expect(api.get).toHaveBeenCalledWith(`/negotiation/runs/${turnResponse.run_key}/`);
  });

  it("fetches a conversation with its bound negotiation payload", async () => {
    const payload = { id: 7, negotiation: { key: "n-key-1" } };
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: payload });
    const res = await getNegotiationConversation(7);
    expect(res.negotiation?.key).toBe("n-key-1");
    expect(api.get).toHaveBeenCalledWith("/negotiation/conversations/7/");
  });

  it("lists the caller's negotiations and fetches one detail", async () => {
    (api.get as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ data: [negotiationRow] })
      .mockResolvedValueOnce({ data: { key: "n-key-1", my_role: "tenant" } });
    const rows = await listNegotiations();
    expect(rows[0].room_price).toBe(8500);
    expect(api.get).toHaveBeenCalledWith("/negotiation/negotiations/");
    const detail = await getNegotiation("n-key-1");
    expect(detail.my_role).toBe("tenant");
    expect(api.get).toHaveBeenLastCalledWith("/negotiation/negotiations/n-key-1/");
  });

  it("approves/rejects an agent proposal through the consent endpoints", async () => {
    (api.post as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ data: { proposal_key: "p-1", status: "approved" } })
      .mockResolvedValueOnce({ data: { proposal_key: "p-1", status: "rejected" } });
    const approved = await approveNegotiationProposal("p-1");
    expect(approved.status).toBe("approved");
    expect(api.post).toHaveBeenCalledWith("/negotiation/proposals/p-1/approve/", { note: "" });
    const rejected = await rejectNegotiationProposal("p-1");
    expect(rejected.status).toBe("rejected");
    expect(api.post).toHaveBeenCalledWith("/negotiation/proposals/p-1/reject/", { note: "" });
  });

  it("rejects/withdraws an offer with its negotiation scoped path", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { ok: "offer_rejected", offer_key: "o-1", status: "rejected" },
    });
    const res = await rejectNegotiationOffer("n-key-1", "o-1");
    expect(res.ok).toBe("offer_rejected");
    expect(api.post).toHaveBeenCalledWith("/negotiation/negotiations/n-key-1/offers/o-1/reject/", {
      note: "",
    });
  });

  it("rejects and cancels a whole negotiation", async () => {
    (api.post as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ data: { ok: "negotiation_rejected", status: "rejected" } })
      .mockResolvedValueOnce({ data: { ok: "negotiation_cancelled", status: "cancelled" } });
    const rejected = await rejectNegotiation("n-key-1");
    expect(rejected.status).toBe("rejected");
    expect(api.post).toHaveBeenCalledWith("/negotiation/negotiations/n-key-1/reject/", {
      note: "",
    });
    const cancelled = await cancelNegotiation("n-key-1");
    expect(cancelled.status).toBe("cancelled");
    expect(api.post).toHaveBeenCalledWith("/negotiation/negotiations/n-key-1/cancel/", {
      note: "",
    });
  });
});
