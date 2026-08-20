/**
 * Component test for the Phase 15 admin revenue centre: summary cards,
 * payout queue tabs, approve/reject wiring and mark-paid with a reference.
 * Hooks are mocked; rendering + action wiring are what's under test.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AdminRevenuePanel from "./AdminRevenuePanel";

vi.mock("../../hooks/useMonetization", () => ({
  useRevenueDashboard: vi.fn(),
  useDecidePayout: vi.fn(),
  useMarkPayoutPaid: vi.fn(),
}));

import {
  useDecidePayout,
  useMarkPayoutPaid,
  useRevenueDashboard,
} from "../../hooks/useMonetization";

const mockDash = useRevenueDashboard as ReturnType<typeof vi.fn>;
const mockDecide = useDecidePayout as ReturnType<typeof vi.fn>;
const mockMarkPaid = useMarkPayoutPaid as ReturnType<typeof vi.fn>;

const pendingPayout = {
  id: 3,
  recipient: 9,
  recipientName: "Rahim Hossain",
  amount: 500,
  method: "bkash",
  accountDetails: {},
  status: "pending",
  reference: "",
  reason: "",
  createdAt: "2025-01-01T00:00:00Z",
  decidedAt: null,
};

const approvedPayout = {
  ...pendingPayout,
  id: 4,
  status: "approved",
  decidedAt: "2025-01-02T00:00:00Z",
};

const dashboard = {
  revenueByScope: [{ scope: "broker", gross: 1000, platform: 20 }],
  totalRevenue: 1000,
  platformRevenue: 20,
  mrr: 400,
  partnerObligations: 980,
  pendingPayouts: { count: 1, total: 500 },
  recentLedger: [
    {
      id: 1,
      entryType: "commission",
      scope: "broker",
      user: 9,
      grossAmount: 100,
      platformAmount: 2,
      partnerAmount: 98,
      currency: "BDT",
      createdAt: "2025-01-01T00:00:00Z",
    },
  ],
  recentCommissions: [],
  recentPayouts: [pendingPayout, approvedPayout],
};

function renderPanel() {
  return render(<AdminRevenuePanel />);
}

describe("AdminRevenuePanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockDash.mockReturnValue({ data: dashboard, isLoading: false });
    mockDecide.mockReturnValue({ isPending: false, mutate: vi.fn() });
    mockMarkPaid.mockReturnValue({ isPending: false, mutate: vi.fn() });
  });

  it("renders summary cards, revenue scopes and the pending payout row", () => {
    renderPanel();
    expect(screen.getByText(/Revenue & payout centre/i)).toBeInTheDocument();
    expect(screen.getByText("৳1,000")).toBeInTheDocument(); // gross revenue
    expect(screen.getAllByText(/broker/i).length).toBeGreaterThan(0);
    expect(screen.getByText("Rahim Hossain")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reject" })).toBeInTheDocument();
  });

  it("approves a pending payout through the decision mutation", async () => {
    const mutate = vi.fn();
    mockDecide.mockReturnValue({ isPending: false, mutate });
    renderPanel();

    await userEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(mutate).toHaveBeenCalledWith({ id: 3, action: "approve" });
  });

  it("switches to the approved tab and marks the payout paid with a reference", async () => {
    const markPaid = vi.fn();
    mockMarkPaid.mockReturnValue({ isPending: false, mutate: markPaid });
    renderPanel();

    await userEvent.click(screen.getByRole("button", { name: "Approved" }));
    expect(screen.getByRole("button", { name: /Mark paid/ })).toBeInTheDocument();

    await userEvent.type(screen.getByPlaceholderText("txn ref"), "ref-42");
    await userEvent.click(screen.getByRole("button", { name: /Mark paid/ }));
    expect(markPaid).toHaveBeenCalledWith({ id: 4, reference: "ref-42" });
  });

  it("shows the ledger entries table", () => {
    renderPanel();
    expect(screen.getByText("Recent ledger entries")).toBeInTheDocument();
    expect(screen.getByText("commission")).toBeInTheDocument();
  });
});
