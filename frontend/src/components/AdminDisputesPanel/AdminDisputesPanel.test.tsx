/**
 * Component test for the admin dispute resolution panel: queue rendering,
 * status transitions and the resolve-with-decision / reject actions.
 */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AdminDisputesPanel from "./AdminDisputesPanel";

vi.mock("../../hooks/useDisputes", () => ({
  useAdminDisputes: vi.fn(),
  useActOnDispute: vi.fn(),
}));

import { useActOnDispute, useAdminDisputes } from "../../hooks/useDisputes";

const mockUseAdmin = useAdminDisputes as ReturnType<typeof vi.fn>;
const mockUseAct = useActOnDispute as ReturnType<typeof vi.fn>;

const openDispute = {
  id: 41,
  booking: 7,
  roomId: 3,
  roomTitle: "Sunlit Studio",
  openedBy: 5,
  openedByUsername: "sabbir.rahman",
  otherPartyUsername: "rahim.hossain",
  category: "deposit",
  categoryDisplay: "Security deposit",
  description: "Deposit not returned after move-out.",
  status: "open",
  statusDisplay: "Open",
  decision: "none",
  decisionDisplay: "No decision",
  decisionAmount: null,
  resolution: "",
  evidence: [
    {
      id: 9,
      dispute: 41,
      uploadedBy: 5,
      uploadedByUsername: "sabbir.rahman",
      kind: "text",
      kindDisplay: "Text statement",
      content: "Left the flat clean on the 1st.",
      file: null,
      createdAt: "2026-01-05T10:00:00Z",
    },
  ],
  createdAt: "2026-01-05T09:00:00Z",
  updatedAt: "2026-01-05T10:00:00Z",
  resolvedAt: null,
};

function renderPanel() {
  return render(<AdminDisputesPanel />);
}

describe("AdminDisputesPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAdmin.mockReturnValue({ data: [], isLoading: false });
    mockUseAct.mockReturnValue({ isPending: false, variables: null, mutateAsync: vi.fn() });
  });

  it("shows the header and empty state", () => {
    renderPanel();
    expect(screen.getByText("Dispute Resolution")).toBeInTheDocument();
    expect(screen.getByText(/no disputes here/i)).toBeInTheDocument();
  });

  it("lists an open dispute with evidence and parties", () => {
    mockUseAdmin.mockReturnValue({ data: [openDispute], isLoading: false });
    renderPanel();
    expect(screen.getByText(/Sunlit Studio/)).toBeInTheDocument();
    expect(screen.getByText(/sabbir.rahman vs rahim.hossain/)).toBeInTheDocument();
    expect(screen.getByText(/Left the flat clean on the 1st/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reject" })).toBeInTheDocument();
  });

  it("transitions a dispute status", async () => {
    mockUseAdmin.mockReturnValue({ data: [openDispute], isLoading: false });
    const mutateAsync = vi.fn().mockResolvedValue({});
    mockUseAct.mockReturnValue({ isPending: false, variables: null, mutateAsync });
    renderPanel();

    // Open the transition select (the first combobox) and pick a status.
    await userEvent.click(screen.getAllByRole("combobox")[0]);
    const listbox = await screen.findByRole("listbox");
    await userEvent.click(within(listbox).getByText("Under review"));
    await userEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(mutateAsync).toHaveBeenCalledWith({
      id: 41,
      payload: { action: "transition", status: "under_review" },
    });
  });

  it("resolves with a deposit refund decision", async () => {
    mockUseAdmin.mockReturnValue({ data: [openDispute], isLoading: false });
    const mutateAsync = vi.fn().mockResolvedValue({});
    mockUseAct.mockReturnValue({ isPending: false, variables: null, mutateAsync });
    renderPanel();

    // Open the decision select (the second combobox) and pick a decision.
    await userEvent.click(screen.getAllByRole("combobox")[1]);
    const listbox = await screen.findByRole("listbox");
    await userEvent.click(within(listbox).getByText("Refund deposit to tenant"));
    await userEvent.type(
      screen.getByLabelText("Resolution note for dispute 41"),
      "Deposit returned in full."
    );
    await userEvent.click(screen.getByRole("button", { name: "Resolve" }));
    expect(mutateAsync).toHaveBeenCalledWith({
      id: 41,
      payload: {
        action: "resolve",
        decision: "refund_to_tenant",
        decisionAmount: null,
        resolution: "Deposit returned in full.",
      },
    });
  });

  it("rejects a dispute", async () => {
    mockUseAdmin.mockReturnValue({ data: [openDispute], isLoading: false });
    const mutateAsync = vi.fn().mockResolvedValue({});
    mockUseAct.mockReturnValue({ isPending: false, variables: null, mutateAsync });
    renderPanel();

    await userEvent.click(screen.getByRole("button", { name: "Reject" }));
    expect(mutateAsync).toHaveBeenCalledWith({
      id: 41,
      payload: { action: "reject", resolution: "" },
    });
  });
});
