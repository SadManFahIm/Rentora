/**
 * Component test for the unified Trust & Safety Operations Center: the
 * overview cards aggregate counts from every queue, and the sub-tabs render
 * the corresponding panels. All hooks are mocked; rendering + wiring are
 * under test.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AdminTrustCenter from "./AdminTrustCenter";

vi.mock("../../hooks/useKyc", () => ({
  useKycSla: vi.fn(),
  usePendingKycApplications: vi.fn(() => ({ data: [], isLoading: false })),
  useReviewKycApplication: vi.fn(() => ({ isPending: false, mutateAsync: vi.fn() })),
  useKycAuditTrail: vi.fn(() => ({ data: [], isLoading: false })),
  usePendingTenantKycApplications: vi.fn(() => ({ data: [], isLoading: false })),
  useReviewTenantKycApplication: vi.fn(() => ({ isPending: false, mutateAsync: vi.fn() })),
}));

vi.mock("../../hooks/useModeration", () => ({
  useModerationOverview: vi.fn(),
  useReviewModerationQueue: vi.fn(() => ({ data: [], isLoading: false })),
  usePhotoModerationQueue: vi.fn(() => ({ data: [], isLoading: false })),
  useDecideReviewModeration: vi.fn(() => ({
    isPending: false,
    variables: null,
    mutateAsync: vi.fn(),
  })),
  useDecidePhotoModeration: vi.fn(() => ({
    isPending: false,
    variables: null,
    mutateAsync: vi.fn(),
  })),
}));

vi.mock("../../hooks/useChat", () => ({
  useAdminReports: vi.fn(() => ({ data: [], isLoading: false })),
  useActOnReport: vi.fn(() => ({ isPending: false, variables: null, mutateAsync: vi.fn() })),
  useChatSafetyEvents: vi.fn(),
}));

vi.mock("../../hooks/useDisputes", () => ({
  useAdminDisputes: vi.fn(() => ({ data: [], isLoading: false })),
  useActOnDispute: vi.fn(() => ({ isPending: false, variables: null, mutateAsync: vi.fn() })),
}));

vi.mock("../../hooks/useAudit", () => ({
  useAuditTrail: vi.fn(),
}));

import { useAuditTrail } from "../../hooks/useAudit";
import { useChatSafetyEvents } from "../../hooks/useChat";
import { useKycSla, usePendingTenantKycApplications } from "../../hooks/useKyc";
import { useModerationOverview } from "../../hooks/useModeration";

const mockKycSla = useKycSla as ReturnType<typeof vi.fn>;
const mockTenantPending = usePendingTenantKycApplications as ReturnType<typeof vi.fn>;
const mockModeration = useModerationOverview as ReturnType<typeof vi.fn>;
const mockSafety = useChatSafetyEvents as ReturnType<typeof vi.fn>;
const mockAudit = useAuditTrail as ReturnType<typeof vi.fn>;

function renderCenter() {
  return render(<AdminTrustCenter />);
}

describe("AdminTrustCenter", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockKycSla.mockReturnValue({ data: { pendingCount: 2 }, isLoading: false });
    mockTenantPending.mockReturnValue({ data: [], isLoading: false });
    mockModeration.mockReturnValue({
      data: {
        reviews: 1,
        reviewsPending: 1,
        reviewsFlagged: 0,
        reviewsApproved: 0,
        reviewsRejected: 0,
        photos: 0,
        photosPending: 0,
        photosFlagged: 0,
        photosApproved: 0,
        photosRejected: 0,
      },
      isLoading: false,
    });
    mockSafety.mockReturnValue({ data: [], isLoading: false });
    mockAudit.mockReturnValue({ data: [], isLoading: false });
  });

  it("shows the overview cards aggregating every queue", () => {
    renderCenter();
    expect(screen.getByText("Trust & Safety Operations Center")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument(); // KYC pending (2 + 0 tenant)
    expect(screen.getByText("1")).toBeInTheDocument(); // moderation pending
    expect(screen.getByText("KYC pending")).toBeInTheDocument();
    expect(screen.getByText("Open reports")).toBeInTheDocument();
    expect(screen.getByText("Moderation pending")).toBeInTheDocument();
    expect(screen.getByText("Open disputes")).toBeInTheDocument();
  });

  it("opens the chat safety feed from the sub-tabs", async () => {
    mockSafety.mockReturnValue({
      data: [
        {
          id: 1,
          chat_room: 3,
          sender_username: "sabbir.rahman",
          sender_name: "Sabbir Rahman",
          risk_level: "critical",
          risk_level_display: "Critical",
          outcome: "blocked",
          outcome_display: "Blocked",
          detectors: [{ key: "payment_redirect", label: "Payment link" }],
          detail: {},
          created_at: "2026-01-05T10:00:00Z",
        },
      ],
      isLoading: false,
    });
    renderCenter();
    await userEvent.click(screen.getByRole("button", { name: "Chat Safety" }));
    expect(screen.getByText("Critical risk")).toBeInTheDocument();
    expect(screen.getByText("Blocked")).toBeInTheDocument();
    expect(screen.getByText("Payment link")).toBeInTheDocument();
  });

  it("opens the audit trail with its entries", async () => {
    mockAudit.mockReturnValue({
      data: [
        {
          id: 9,
          actor: 1,
          actorUsername: "admin",
          action: "moderation.review.approve",
          targetType: "moderation.ReviewModeration",
          targetId: "11",
          detail: {},
          ipAddress: null,
          createdAt: "2026-01-05T10:00:00Z",
        },
      ],
      isLoading: false,
    });
    renderCenter();
    await userEvent.click(screen.getByRole("button", { name: "Audit Trail" }));
    expect(screen.getByText("moderation.review.approve")).toBeInTheDocument();
    expect(screen.getByText(/admin · moderation.ReviewModeration #11/)).toBeInTheDocument();
  });

  it("opens the reports queue panel", async () => {
    renderCenter();
    await userEvent.click(screen.getByRole("button", { name: "Reports" }));
    expect(screen.getByText("Report Moderation Queue")).toBeInTheDocument();
  });
});
