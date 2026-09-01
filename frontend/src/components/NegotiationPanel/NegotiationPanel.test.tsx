/**
 * Component test for the Phase 19.4 NegotiationPanel. The hook is mocked; the
 * rendering of negotiation summary, offer actions (withdraw / reject /
 * ask-agent-to-accept), consent cards, the negotiation rail and the chat input
 * are what's under test.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { NegotiationPayload, NegotiationRow } from "../../services/negotiationAgentService";
import type { UseNegotiationAgentReturn } from "../../hooks/useNegotiationAgent";
import NegotiationPanel from "./NegotiationPanel";

vi.mock("../../hooks/useNegotiationAgent", () => ({
  default: vi.fn(),
}));

import useNegotiationAgent from "../../hooks/useNegotiationAgent";

const mockUseNegotiationAgent = useNegotiationAgent as unknown as ReturnType<typeof vi.fn>;

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
    amenities: ["WiFi"],
    address: "Sector 10, Uttara",
    verified: true,
    featured: false,
    available: true,
    lat: 23.87,
    lng: 90.36,
    image: null,
    url: "/rooms/29",
  },
  insights: null,
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
      key: "o-sent-mine",
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

const proposal = {
  key: "p-1",
  tool: "negotiation.create_offer",
  status: "pending" as const,
  approval_required: "user",
  room: null,
  summary: "Create offer of ৳8,000/month.",
  created_at: null,
  expires_at: null,
  reviewed_at: null,
  conversation_id: 7,
};

function stateOverrides(overrides: Partial<UseNegotiationAgentReturn> = {}) {
  return {
    messages: [],
    proposals: [] as (typeof proposal)[],
    suggestions: [],
    conversationId: null,
    sending: false,
    acting: false,
    error: "",
    featureEnabled: true,
    agentName: "Negotiation Agent",
    agentDescription: "",
    lastAction: "",
    negotiations: [row],
    activeKey: "n-key-1",
    negotiation,
    negotiationLoading: false,
    send: vi.fn(async () => undefined),
    reply: vi.fn(async () => undefined),
    approve: vi.fn(async () => undefined),
    reject: vi.fn(async () => undefined),
    openRoom: vi.fn(async () => ({ id: 29 }) as never),
    reset: vi.fn(async () => undefined),
    select: vi.fn(async () => undefined),
    withdrawOffer: vi.fn(async () => undefined),
    rejectOffer: vi.fn(async () => undefined),
    rejectWhole: vi.fn(async () => undefined),
    cancelWhole: vi.fn(async () => undefined),
    ...overrides,
  };
}

describe("NegotiationPanel (Phase 19.4)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the negotiation summary: status, room, counterparty and price range", () => {
    mockUseNegotiationAgent.mockReturnValue(stateOverrides());
    render(<NegotiationPanel />);

    // room name appears in both the rail and the summary header
    expect(screen.getAllByText("Student Room, Uttara Sector 10").length).toBeGreaterThan(0);
    expect(screen.getByText(/Listed ৳8,500/)).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText(/৳7,500–৳8,500/)).toBeInTheDocument();
  });

  it("shows the feature-off banner when the flag is disabled", () => {
    mockUseNegotiationAgent.mockReturnValue(stateOverrides({ featureEnabled: false }));
    render(<NegotiationPanel />);

    expect(screen.getByText(/ai\.negotiation_agent/)).toBeInTheDocument();
  });

  it("hides the negotiations rail when scoped to a single room", () => {
    mockUseNegotiationAgent.mockReturnValue(stateOverrides());
    render(<NegotiationPanel roomId={29} />);

    expect(screen.queryByText("Negotiations")).not.toBeInTheDocument();
  });

  it("shows the rail on the dashboard and switches negotiations", async () => {
    const withSecond = {
      key: "n-key-2",
      room_id: 30,
      room_title: "AC Studio, Dhanmondi",
      room_price: 12000,
      status: "offer_pending",
      my_role: "tenant",
      peer_name: "Nadia",
      updated_at: "2026-09-02T10:00:00Z",
      last_offer: null,
    };
    const overrides = stateOverrides({ negotiations: [row, withSecond as NegotiationRow] });
    mockUseNegotiationAgent.mockReturnValue(overrides);
    render(<NegotiationPanel />);

    const other = screen.getByRole("button", { name: /AC Studio, Dhanmondi/ });
    await userEvent.click(other);
    expect(overrides.select).toHaveBeenCalledWith("n-key-2");
  });

  it("lets the sender withdraw their outstanding offer", async () => {
    const overrides = stateOverrides();
    mockUseNegotiationAgent.mockReturnValue(overrides);
    render(<NegotiationPanel />);

    await userEvent.click(screen.getByRole("button", { name: "Withdraw this offer" }));
    expect(overrides.withdrawOffer).toHaveBeenCalledWith("o-sent-mine");
  });

  it("lets the counterparty reject an outstanding offer", async () => {
    const counterpartOffer = {
      ...negotiation.offers[0],
      key: "o-counter",
      sender_role: "landlord" as const,
      sender_name: "Sadman",
      can_withdraw: false,
      can_accept: true,
      can_reject: true,
    };
    const payload = { ...negotiation, offers: [counterpartOffer] };
    const overrides = stateOverrides({ negotiation: payload });
    mockUseNegotiationAgent.mockReturnValue(overrides);
    render(<NegotiationPanel />);

    await userEvent.click(screen.getByRole("button", { name: "Reject this offer" }));
    expect(overrides.rejectOffer).toHaveBeenCalledWith("o-counter");
  });

  it("asks the agent to accept a counterpart offer (consent-gated via chat)", async () => {
    const counterpartOffer = {
      ...negotiation.offers[0],
      key: "o-counter",
      sender_role: "landlord" as const,
      sender_name: "Sadman",
      can_withdraw: false,
      can_accept: true,
      can_reject: true,
    };
    const payload = { ...negotiation, offers: [counterpartOffer] };
    const overrides = stateOverrides({ negotiation: payload });
    mockUseNegotiationAgent.mockReturnValue(overrides);
    render(<NegotiationPanel />);

    await userEvent.click(
      screen.getByRole("button", { name: "Ask the agent to accept this offer" })
    );
    expect(overrides.send).toHaveBeenCalledWith(
      expect.stringContaining("Please accept the offer of")
    );
  });

  it("rejects or cancels the whole negotiation", async () => {
    const overrides = stateOverrides();
    mockUseNegotiationAgent.mockReturnValue(overrides);
    render(<NegotiationPanel />);

    await userEvent.click(screen.getByRole("button", { name: "Reject negotiation" }));
    expect(overrides.rejectWhole).toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(overrides.cancelWhole).toHaveBeenCalled();
  });

  it("renders a pending consent card and approves/rejects it", async () => {
    const overrides = stateOverrides({ proposals: [proposal] });
    mockUseNegotiationAgent.mockReturnValue(overrides);
    render(<NegotiationPanel />);

    expect(screen.getByText("1 step await your approval")).toBeInTheDocument();
    expect(screen.getByText("create offer")).toBeInTheDocument();
    expect(screen.getByText("Create offer of ৳8,000/month.")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(overrides.approve).toHaveBeenCalledWith("p-1");
  });

  it("sends a typed chat turn and disables input while the agent is working", async () => {
    const overrides = stateOverrides({ sending: true });
    mockUseNegotiationAgent.mockReturnValue(overrides);
    const first = render(<NegotiationPanel />);

    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    first.unmount();

    const sendingState = stateOverrides();
    mockUseNegotiationAgent.mockReturnValue(sendingState);
    render(<NegotiationPanel />);

    await userEvent.type(
      screen.getByRole("textbox", { name: "Message the negotiation agent" }),
      "Counter that please"
    );
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(sendingState.send).toHaveBeenCalledWith("Counter that please");
  });

  it("clears the chat with New chat", async () => {
    const overrides = stateOverrides();
    mockUseNegotiationAgent.mockReturnValue(overrides);
    render(<NegotiationPanel />);

    await userEvent.click(screen.getByRole("button", { name: "New chat" }));
    expect(overrides.reset).toHaveBeenCalled();
  });
});
