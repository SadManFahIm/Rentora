import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { NegotiationPayload, NegotiationRow } from "../services/negotiationAgentService";
import type { RentalAgentRun } from "../services/rentalAgentService";

vi.mock("../services/negotiationAgentService", () => ({
  approveNegotiationProposal: vi.fn(),
  cancelNegotiation: vi.fn(),
  getNegotiation: vi.fn(),
  getNegotiationConversation: vi.fn(),
  getNegotiationRun: vi.fn(),
  listNegotiationConversations: vi.fn(),
  listNegotiations: vi.fn(),
  rejectNegotiation: vi.fn(),
  rejectNegotiationOffer: vi.fn(),
  rejectNegotiationProposal: vi.fn(),
  sendNegotiationTurn: vi.fn(),
}));

import useNegotiationAgent from "./useNegotiationAgent";
import {
  approveNegotiationProposal,
  getNegotiation,
  getNegotiationConversation,
  getNegotiationRun,
  listNegotiationConversations,
  listNegotiations,
  rejectNegotiation,
  rejectNegotiationOffer,
  sendNegotiationTurn,
} from "../services/negotiationAgentService";

const mockGetNegotiation = getNegotiation as ReturnType<typeof vi.fn>;
const mockGetNegotiationConversation = getNegotiationConversation as ReturnType<typeof vi.fn>;
const mockGetNegotiationRun = getNegotiationRun as ReturnType<typeof vi.fn>;
const mockListNegotiationConversations = listNegotiationConversations as ReturnType<typeof vi.fn>;
const mockListNegotiations = listNegotiations as ReturnType<typeof vi.fn>;
const mockSendNegotiationTurn = sendNegotiationTurn as ReturnType<typeof vi.fn>;
const mockApproveNegotiationProposal = approveNegotiationProposal as ReturnType<typeof vi.fn>;
const mockRejectNegotiation = rejectNegotiation as ReturnType<typeof vi.fn>;
const mockRejectNegotiationOffer = rejectNegotiationOffer as ReturnType<typeof vi.fn>;

const row: NegotiationRow = {
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

const negotiation: NegotiationPayload = {
  key: "n-key-1",
  room_id: 29,
  room: {
    id: 29,
    title: "Student Room, Uttara Sector 10",
    price_bdt: 8500,
    price_text: "৳8,500/month",
    currency: "BDT",
    area: "Uttara",
    area_display: "Uttara",
    room_type: "single",
    room_type_display: "Single",
    gender_preference: "any",
    size_sqft: 220,
    amenities: ["WiFi", "Furnished"],
    address: "Sector 10, Uttara",
    verified: true,
    featured: false,
    available: true,
    lat: 23.87,
    lng: 90.36,
    image: null,
    url: "/rooms/29",
  },
  insights: { insights: ["Fair price range 8,000–9,000"], source: "smart" },
  status: "active",
  status_label: "Active",
  my_role: "tenant",
  tenant: { name: "Tenant User" },
  landlord: { name: "Sadman", is_owner: true },
  peer_name: "Sadman",
  my_constraints: { min_amount: 7500, max_amount: 8500 },
  peer_constraints_set: true,
  offers: [
    {
      key: "o-1",
      kind: "offer",
      amount: 8000,
      message: "Monthly rent offer",
      meta: {},
      status: "sent",
      sender_role: "tenant",
      sender_name: "Tenant User",
      created_at: "2026-09-01T09:00:00Z",
      expires_at: "2026-09-08T09:00:00Z",
      can_accept: false,
      can_reject: false,
      can_withdraw: true,
    },
  ],
  timeline: [
    {
      event: "negotiation_initiated",
      actor_name: "Tenant User",
      detail: {},
      created_at: "2026-09-01T08:00:00Z",
    },
  ],
  expires_at: "2026-10-01T08:00:00Z",
  is_open: true,
  features: { negotiation_agent_enabled: true },
  chat_room_id: null,
  can_reject: true,
  can_cancel: true,
};

const runCompleted: RentalAgentRun = {
  key: "run-1",
  status: "completed",
  termination_reason: "",
  error_message: "",
  turn_count: 3,
  tool_call_count: 2,
  created_at: "2026-09-01T09:00:00Z",
  completed_at: "2026-09-01T09:00:05Z",
};

const conversationPayload = {
  id: 7,
  title: "Negotiation — Student Room, Uttara Sector 10",
  status: "active",
  feature_enabled: true,
  agent: { key: "ai.negotiation_agent", name: "Negotiation Agent", description: "" },
  latest_run: runCompleted,
  messages: [
    {
      id: 1,
      role: "assistant",
      content: "I can draft an offer for you.",
      created_at: null,
      cards: [],
    },
    {
      id: 2,
      role: "user",
      content: "Draft an offer of ৳8,000 please.",
      created_at: null,
      cards: [],
    },
  ],
  proposals: [],
  suggestions: [{ label: "Ask for a counter", text: "Ask the landlord for a counter" }],
  negotiation,
};

describe("useNegotiationAgent (Phase 19.4)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("starts in a welcome state when the caller has no negotiations", async () => {
    mockListNegotiations.mockResolvedValueOnce([]);
    const { result } = renderHook(() => useNegotiationAgent());
    await waitFor(() => expect(result.current.negotiations).toEqual([]));
    expect(result.current.activeKey).toBeNull();
    expect(result.current.negotiation).toBeNull();
    expect(result.current.messages).toEqual([]);
  });

  it("auto-selects the most recent negotiation as a participant", async () => {
    mockListNegotiations.mockResolvedValueOnce([row]);
    mockGetNegotiation.mockResolvedValueOnce(negotiation);
    mockListNegotiationConversations.mockResolvedValueOnce([]);

    const { result } = renderHook(() => useNegotiationAgent());
    await waitFor(() => expect(result.current.negotiation?.key).toBe("n-key-1"));

    expect(result.current.activeKey).toBe("n-key-1");
    expect(result.current.featureEnabled).toBe(true);
    expect(mockGetNegotiation).toHaveBeenCalledWith("n-key-1");
    // no bound conversation → transcript stays clean, first turn binds via room_id
    expect(mockGetNegotiationConversation).not.toHaveBeenCalled();
  });

  it("with a roomId and no negotiation stays ready to start one", async () => {
    mockListNegotiations.mockResolvedValueOnce([]);
    const { result } = renderHook(() => useNegotiationAgent(29));
    await waitFor(() => expect(result.current.negotiations).toEqual([]));
    expect(result.current.negotiation).toBeNull();
    expect(result.current.messages).toEqual([]);
  });

  it("resumes an existing bound conversation when selecting a negotiation", async () => {
    mockListNegotiations.mockResolvedValue([row]);
    mockGetNegotiation.mockResolvedValue(negotiation);
    mockListNegotiationConversations.mockResolvedValue([
      { id: 7, title: "", status: "active", last_activity_at: null },
    ]);
    mockGetNegotiationConversation.mockResolvedValue(conversationPayload);

    const { result } = renderHook(() => useNegotiationAgent());
    await waitFor(() => expect(result.current.negotiation?.key).toBe("n-key-1"));
    // resolution scan + transcript load both hit the conversation detail
    await waitFor(() => expect(mockGetNegotiationConversation).toHaveBeenCalledTimes(2));
    expect(result.current.messages).toHaveLength(2);
    expect(result.current.conversationId).toBe(7);
  });

  it("sends a turn via room_id when no conversation is bound yet", async () => {
    mockListNegotiations.mockResolvedValue([row]);
    mockGetNegotiation.mockResolvedValue(negotiation);
    mockListNegotiationConversations.mockResolvedValue([]);
    mockSendNegotiationTurn.mockResolvedValue({
      conversation_id: 7,
      run_key: "run-1",
      status: "pending",
      task_id: "t",
    });
    mockGetNegotiationRun.mockResolvedValue(runCompleted);
    mockGetNegotiationConversation.mockResolvedValue(conversationPayload);

    const { result } = renderHook(() => useNegotiationAgent());
    await waitFor(() => expect(result.current.negotiation?.key).toBe("n-key-1"));

    await act(async () => {
      await result.current.send("Draft an offer of ৳8,000 please.");
    });

    expect(mockSendNegotiationTurn).toHaveBeenCalledWith("Draft an offer of ৳8,000 please.", {
      roomId: 29,
    });
    expect(result.current.messages).toHaveLength(2);
    expect(result.current.error).toBe("");
  });

  it("continues an existing conversation by id once bound", async () => {
    mockListNegotiations.mockResolvedValue([row]);
    mockGetNegotiation.mockResolvedValue(negotiation);
    mockListNegotiationConversations.mockResolvedValue([]);
    mockSendNegotiationTurn.mockResolvedValue({
      conversation_id: 7,
      run_key: "run-1",
      status: "pending",
      task_id: "t",
    });
    mockGetNegotiationRun.mockResolvedValue(runCompleted);
    mockGetNegotiationConversation.mockResolvedValue(conversationPayload);

    const { result } = renderHook(() => useNegotiationAgent());
    await waitFor(() => expect(result.current.negotiation?.key).toBe("n-key-1"));

    await act(async () => {
      await result.current.send("First message");
    });
    mockGetNegotiationRun.mockResolvedValue(runCompleted);
    mockSendNegotiationTurn.mockClear();

    await act(async () => {
      await result.current.send("Second message");
    });

    expect(mockSendNegotiationTurn).toHaveBeenCalledWith("Second message", {
      conversationId: 7,
    });
  });

  it("approve dispatches participant consent then reloads the payload", async () => {
    const withProposal = {
      ...conversationPayload,
      proposals: [
        {
          key: "p-1",
          tool: "negotiation.create_offer",
          status: "pending",
          approval_required: "user",
          room: null,
          summary: "Create offer ৳8,000.",
          created_at: null,
          expires_at: null,
          reviewed_at: null,
          conversation_id: 7,
        },
      ],
    };
    mockListNegotiations.mockResolvedValue([row]);
    mockGetNegotiation.mockResolvedValue(negotiation);
    mockListNegotiationConversations.mockResolvedValue([
      { id: 7, title: "", status: "active", last_activity_at: null },
    ]);
    mockGetNegotiationConversation.mockResolvedValue(withProposal);
    mockApproveNegotiationProposal.mockResolvedValue({ proposal_key: "p-1", status: "approved" });

    const { result } = renderHook(() => useNegotiationAgent());
    await waitFor(() => expect(result.current.negotiation?.key).toBe("n-key-1"));
    await waitFor(() => expect(result.current.proposals).toHaveLength(1));

    await act(async () => {
      await result.current.approve("p-1");
    });

    expect(mockApproveNegotiationProposal).toHaveBeenCalledWith("p-1");
    expect(result.current.proposals).toHaveLength(1);
    expect(result.current.error).toBe("");
  });

  it("reject negotiation and withdraw own offer hit the scoped endpoints", async () => {
    mockListNegotiations.mockResolvedValue([row]);
    mockGetNegotiation.mockResolvedValue(negotiation);
    mockListNegotiationConversations.mockResolvedValue([]);
    mockRejectNegotiation.mockResolvedValue({ ok: "negotiation_rejected", status: "rejected" });
    mockRejectNegotiationOffer.mockResolvedValue({
      ok: "offer_withdrawn",
      offer_key: "o-1",
      status: "withdrawn",
    });

    const { result } = renderHook(() => useNegotiationAgent());
    await waitFor(() => expect(result.current.negotiation?.key).toBe("n-key-1"));

    await act(async () => {
      await result.current.rejectWhole();
    });
    expect(mockRejectNegotiation).toHaveBeenCalledWith("n-key-1", "");

    await act(async () => {
      await result.current.withdrawOffer("o-1");
    });
    expect(mockRejectNegotiationOffer).toHaveBeenCalledWith("n-key-1", "o-1", "");
  });
});
