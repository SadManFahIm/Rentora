/**
 * Component test for the Phase 12.4 report moderation queue: summary counts,
 * status tabs, per-report actions (dismiss / warn with a note / suspend with
 * confirmation) and the empty state. Hooks are mocked; rendering + action
 * wiring are what's under test.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AdminReportsPanel from "./AdminReportsPanel";

vi.mock("../../hooks/useChat", () => ({
  useAdminReports: vi.fn(),
  useActOnReport: vi.fn(),
}));

import { useActOnReport, useAdminReports } from "../../hooks/useChat";

const mockUseReports = useAdminReports as ReturnType<typeof vi.fn>;
const mockUseAct = useActOnReport as ReturnType<typeof vi.fn>;

const openReport = {
  id: 31,
  reporterUsername: "nadia.islam",
  reporterName: "Nadia Islam",
  targetUserId: 5,
  targetUsername: "sabbir.rahman",
  targetName: "Sabbir Rahman",
  messageId: 88,
  category: "payment_fraud",
  categoryDisplay: "Payment fraud",
  description: "Asked me to send rent outside the app.",
  status: "open",
  statusDisplay: "Open",
  actionTaken: "",
  actionTakenDisplay: "—",
  adminNote: "",
  createdAt: "2025-01-05T10:00:00Z",
  resolvedAt: null,
};

function renderPanel() {
  return render(<AdminReportsPanel />);
}

describe("AdminReportsPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseReports.mockReturnValue({ data: [], isLoading: false });
    mockUseAct.mockReturnValue({ isPending: false, variables: null, mutateAsync: vi.fn() });
  });

  it("shows the header and an empty state when there are no reports", () => {
    renderPanel();
    expect(screen.getByText("Report Moderation Queue")).toBeInTheDocument();
    expect(screen.getByText(/no open reports/i)).toBeInTheDocument();
  });

  it("lists an open report with its category, message anchor and actions", async () => {
    mockUseReports.mockReturnValue({ data: [openReport], isLoading: false });
    const mutateAsync = vi.fn().mockResolvedValue({});
    mockUseAct.mockReturnValue({ isPending: false, variables: null, mutateAsync });
    renderPanel();

    expect(screen.getByText("Sabbir Rahman")).toBeInTheDocument();
    expect(screen.getByText("Payment fraud")).toBeInTheDocument();
    expect(screen.getByText(/message #88/)).toBeInTheDocument();
    expect(screen.getByText("Asked me to send rent outside the app.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Dismiss" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Warn" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Escalate" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Suspend" })).toBeInTheDocument();
  });

  it("dismisses a report with the auditable action", async () => {
    mockUseReports.mockReturnValue({ data: [openReport], isLoading: false });
    const mutateAsync = vi.fn().mockResolvedValue({});
    mockUseAct.mockReturnValue({ isPending: false, variables: null, mutateAsync });
    renderPanel();

    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(mutateAsync).toHaveBeenCalledWith({ reportId: 31, action: "dismiss", note: "" });
  });

  it("passes the admin note through when warning a user", async () => {
    mockUseReports.mockReturnValue({ data: [openReport], isLoading: false });
    const mutateAsync = vi.fn().mockResolvedValue({});
    mockUseAct.mockReturnValue({ isPending: false, variables: null, mutateAsync });
    renderPanel();

    await userEvent.type(screen.getByLabelText("Note for report 31"), "Keep it polite");
    await userEvent.click(screen.getByRole("button", { name: "Warn" }));
    expect(mutateAsync).toHaveBeenCalledWith({
      reportId: 31,
      action: "warn",
      note: "Keep it polite",
    });
  });

  it("confirms before suspending the reported account", async () => {
    mockUseReports.mockReturnValue({ data: [openReport], isLoading: false });
    const mutateAsync = vi.fn().mockResolvedValue({});
    mockUseAct.mockReturnValue({ isPending: false, variables: null, mutateAsync });
    renderPanel();

    await userEvent.click(screen.getByRole("button", { name: "Suspend" }));
    expect(screen.getByText(/Suspend Sabbir Rahman\?/i)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Suspend account" }));
    expect(mutateAsync).toHaveBeenCalledWith({ reportId: 31, action: "suspend", note: "" });
  });

  it("filters the queue by status tab and shows summary counts", async () => {
    const resolved = {
      ...openReport,
      id: 32,
      status: "resolved",
      statusDisplay: "Resolved",
      actionTaken: "warn",
      actionTakenDisplay: "Warned",
    };
    mockUseReports.mockReturnValue({ data: [openReport, resolved], isLoading: false });
    mockUseAct.mockReturnValue({ isPending: false, variables: null, mutateAsync: vi.fn() });
    renderPanel();

    // Open tab is default: only the open report is listed.
    expect(screen.getByText("Sabbir Rahman")).toBeInTheDocument();
    expect(screen.queryByText(/No open reports/)).not.toBeInTheDocument();

    // Summary cards reflect counts.
    expect(screen.getAllByText("1")).toHaveLength(2); // Open + Resolved cards

    // Switching to the All tab shows both rows.
    await userEvent.click(screen.getByRole("button", { name: /All/ }));
    expect(screen.getByText(/action: Warned/i)).toBeInTheDocument();
  });
});
