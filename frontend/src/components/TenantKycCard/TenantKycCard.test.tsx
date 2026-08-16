import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { TenantVerification } from "../../types";
import TenantKycCard from "./TenantKycCard";

vi.mock("../../hooks/useKyc", () => ({
  useMyTenantVerification: vi.fn(),
  useSubmitTenantVerification: vi.fn(),
}));

import { useMyTenantVerification, useSubmitTenantVerification } from "../../hooks/useKyc";

const mockUseMine = useMyTenantVerification as ReturnType<typeof vi.fn>;
const mockUseSubmit = useSubmitTenantVerification as ReturnType<typeof vi.fn>;

const verifiedRecord: TenantVerification = {
  id: 1,
  status: "verified",
  statusDisplay: "Verified",
  docType: "nid",
  docTypeDisplay: "National ID (NID)",
  fileUrl: "http://test/api/v1/users/tenant-kyc/1/file/",
  reviewNote: "",
  createdAt: "2026-08-01T00:00:00Z",
  updatedAt: "2026-08-01T00:00:00Z",
  reviewedAt: "2026-08-01T00:00:00Z",
  expiresAt: "2027-08-01T00:00:00Z",
  autoScreenScore: null,
  autoScreenResult: null,
  autoScreenDetail: { reasons: [] },
};

const rejectedRecord: TenantVerification = {
  ...verifiedRecord,
  status: "rejected",
  statusDisplay: "Rejected",
  reviewNote: "Blurry scan — please re-upload.",
  reviewedAt: "2026-08-02T00:00:00Z",
};

function renderCard(record: TenantVerification | null = null) {
  mockUseMine.mockReturnValue({ data: record, isLoading: false });
  mockUseSubmit.mockReturnValue({ isPending: false, mutateAsync: vi.fn() });
  return render(<TenantKycCard />);
}

describe("TenantKycCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows the upload form for a tenant who never started", () => {
    renderCard(null);
    expect(screen.getByText("Tenant Verification")).toBeInTheDocument();
    expect(screen.getByLabelText("Tenant verification document file")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /submit/i })).toBeInTheDocument();
  });

  it("shows a reviewing state with no upload form while pending", () => {
    renderCard({ ...verifiedRecord, status: "pending", statusDisplay: "Pending" });
    expect(screen.getByText("Reviewing")).toBeInTheDocument();
    expect(screen.queryByLabelText("Tenant verification document file")).not.toBeInTheDocument();
  });

  it("shows the verified banner with the badge and no upload form", () => {
    renderCard(verifiedRecord);
    // The badge chip (exact text) next to the banner copy that starts "Verified —".
    expect(screen.getAllByText(/^Verified$/).length).toBeGreaterThan(0);
    expect(screen.getByText(/landlords see the verified-tenant badge/i)).toBeInTheDocument();
    expect(screen.queryByLabelText("Tenant verification document file")).not.toBeInTheDocument();
  });

  it("shows the reviewer note and a re-submit button after rejection", () => {
    renderCard(rejectedRecord);
    expect(screen.getByText("Reviewer note")).toBeInTheDocument();
    expect(screen.getByText(/Blurry scan/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /re-submit/i })).toBeInTheDocument();
  });

  it("shows needs_review with the note and a re-submit form", () => {
    renderCard({
      ...rejectedRecord,
      status: "needs_review",
      statusDisplay: "Needs Review",
    });
    expect(screen.getByText(/needs attention/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /re-submit/i })).toBeInTheDocument();
  });

  it("shows the expired state with a fresh upload form", () => {
    renderCard({ ...verifiedRecord, status: "expired", statusDisplay: "Expired" });
    expect(screen.getByText(/previous verification expired/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /re-submit/i })).toBeInTheDocument();
  });
});
