/**
 * Component test for the admin KYC panel: the SLA queue-health stats, the
 * applications queue and the audit-trail history view. Hooks are mocked;
 * rendering + the Applications/History toggle are what's under test.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AdminKycPanel from "./AdminKycPanel";

vi.mock("../../hooks/useKyc", () => ({
  usePendingKycApplications: vi.fn(),
  useReviewKycApplication: vi.fn(),
  useKycSla: vi.fn(),
  useKycAuditTrail: vi.fn(),
}));

vi.mock("../../services/kycService", () => ({
  kycService: { fetchDocumentFile: vi.fn() },
}));

import {
  useKycAuditTrail,
  useKycSla,
  usePendingKycApplications,
  useReviewKycApplication,
} from "../../hooks/useKyc";

const mockUsePending = usePendingKycApplications as ReturnType<typeof vi.fn>;
const mockUseReview = useReviewKycApplication as ReturnType<typeof vi.fn>;
const mockUseSla = useKycSla as ReturnType<typeof vi.fn>;
const mockUseAudit = useKycAuditTrail as ReturnType<typeof vi.fn>;

const emptyApp = {
  id: 1,
  username: "kyc_landlord",
  email: "kyc_landlord@example.com",
  name: "KYC Landlord",
  phone: "",
  role: "landlord",
  nidVerified: false,
  documents: [],
};

const sla = {
  pendingCount: 3,
  resolvedCount: 12,
  avgReviewHours: 6.5,
  last7dDecisions: 8,
  last7dAvgReviewHours: 4.2,
  prev7dDecisions: 5,
  decisionDelta7d: 3,
  pendingOldestHours: 30,
};

function renderPanel() {
  return render(<AdminKycPanel />);
}

describe("AdminKycPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUsePending.mockReturnValue({ data: [], isLoading: false });
    mockUseReview.mockReturnValue({ isPending: false, mutateAsync: vi.fn() });
    mockUseSla.mockReturnValue({ data: sla, isLoading: false });
    mockUseAudit.mockReturnValue({ data: [], isLoading: false });
  });

  it("shows the SLA queue-health stats on the Applications view", () => {
    renderPanel();

    expect(screen.getByText("Pending applications")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("oldest waiting 1.3d")).toBeInTheDocument();
    expect(screen.getByText("Avg review time")).toBeInTheDocument();
    expect(screen.getByText("7h")).toBeInTheDocument();
    expect(screen.getByText("4h this week")).toBeInTheDocument();
    expect(screen.getByText("Decisions · 7 days")).toBeInTheDocument();
    expect(screen.getByText("▲ +3 vs last week")).toBeInTheDocument();
  });

  it("lists pending applications with an approve action", async () => {
    const mutateAsync = vi.fn().mockResolvedValue({});
    mockUsePending.mockReturnValue({ data: [emptyApp], isLoading: false });
    mockUseReview.mockReturnValue({ isPending: false, mutateAsync });
    renderPanel();

    expect(screen.getByText("KYC Landlord")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reject" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(mutateAsync).toHaveBeenCalledWith({ userId: 1, approved: true, note: "" });
  });

  it("switches to the audit-trail history view", async () => {
    mockUseAudit.mockReturnValue({
      data: [
        {
          id: 9,
          action: "kyc.approved",
          actorUsername: "admin",
          actorName: "Admin",
          userId: 1,
          userName: "KYC Landlord",
          note: "Docs look genuine",
          createdAt: "2026-01-09T10:00:00Z",
        },
      ],
      isLoading: false,
    });
    renderPanel();

    await userEvent.click(screen.getByRole("button", { name: /history/i }));

    expect(screen.getByText("Approved")).toBeInTheDocument();
    expect(screen.getByText(/Docs look genuine/)).toBeInTheDocument();
    expect(screen.queryByText("Pending applications")).not.toBeInTheDocument();
  });
});
