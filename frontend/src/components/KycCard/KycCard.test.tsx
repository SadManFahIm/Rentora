/**
 * Component test for the dashboard KYC card: verification status states and
 * the document upload flow. Hooks are mocked; rendering + interactions are
 * what's under test.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { KycDocument } from "../../types";
import KycCard from "./KycCard";

vi.mock("../../hooks/useKyc", () => ({
  useMyKycDocuments: vi.fn(),
  useUploadKycDocument: vi.fn(),
}));

vi.mock("../../context/AppContext", () => ({
  useApp: vi.fn(),
}));

import { useApp } from "../../context/AppContext";
import { useMyKycDocuments, useUploadKycDocument } from "../../hooks/useKyc";

const mockUseApp = useApp as ReturnType<typeof vi.fn>;
const mockUseDocs = useMyKycDocuments as ReturnType<typeof vi.fn>;
const mockUseUpload = useUploadKycDocument as ReturnType<typeof vi.fn>;

const pendingDoc: KycDocument = {
  id: 1,
  docType: "nid",
  docTypeDisplay: "National ID (NID)",
  fileUrl: "http://testserver/media/kyc_documents/nid.jpg",
  status: "pending",
  statusDisplay: "Pending",
  reviewNote: "",
  createdAt: "2026-01-05T10:00:00Z",
  reviewedAt: null,
};

const rejectedDoc: KycDocument = {
  ...pendingDoc,
  id: 2,
  status: "rejected",
  statusDisplay: "Rejected",
  reviewNote: "Blurry scan — please re-upload",
  reviewedAt: "2026-01-06T10:00:00Z",
};

const emptyNoteRejectedDoc: KycDocument = {
  ...rejectedDoc,
  id: 3,
  reviewNote: "",
  reviewedAt: "2026-01-07T10:00:00Z",
};

function renderKycCard(userRole: "landlord" | "tenant" = "landlord") {
  mockUseApp.mockReturnValue({ user: { role: userRole, nidVerified: false } });
  return render(<KycCard />);
}

describe("KycCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseDocs.mockReturnValue({ data: [], isLoading: false });
    mockUseUpload.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
    });
  });

  it("shows a verified banner with no upload form for verified users", () => {
    mockUseApp.mockReturnValue({ user: { role: "landlord", nidVerified: true } });
    render(<KycCard />);

    expect(
      screen.getByText(
        "Verified — your listings carry the trust badge and rank above unverified landlords."
      )
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Upload" })).not.toBeInTheDocument();
  });

  it("shows the upload form when unverified with no documents", () => {
    renderKycCard();

    expect(screen.getByRole("button", { name: "Upload" })).toBeInTheDocument();
    expect(screen.getByLabelText("KYC document file")).toBeInTheDocument();
    expect(screen.getByText("National ID (NID)")).toBeInTheDocument();
  });

  it("shows 'under review' and hides the upload form while a document is pending", () => {
    mockUseDocs.mockReturnValue({ data: [pendingDoc], isLoading: false });
    renderKycCard();

    expect(screen.getByText(/Your document is under review/)).toBeInTheDocument();
    expect(screen.getByText("Pending")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Upload" })).not.toBeInTheDocument();
  });

  it("lists a rejected document and allows re-upload", () => {
    mockUseDocs.mockReturnValue({ data: [rejectedDoc], isLoading: false });
    renderKycCard();

    expect(screen.getByText("Rejected")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload" })).toBeInTheDocument();
  });

  it("shows the reviewer's rejection note so the landlord knows what to fix", () => {
    mockUseDocs.mockReturnValue({ data: [rejectedDoc], isLoading: false });
    renderKycCard();

    expect(screen.getByText("Why it was rejected")).toBeInTheDocument();
    expect(screen.getByText(/Blurry scan — please re-upload/)).toBeInTheDocument();
    expect(screen.getByText(/was not approved/)).toBeInTheDocument();
  });

  it("does not show the rejection banner while a newer document is pending", () => {
    mockUseDocs.mockReturnValue({ data: [rejectedDoc, pendingDoc], isLoading: false });
    renderKycCard();

    expect(screen.queryByText("Why it was rejected")).not.toBeInTheDocument();
    expect(screen.getByText(/under review/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Upload" })).not.toBeInTheDocument();
  });

  it("shows the note from the most recently rejected document", () => {
    const olderRejected: KycDocument = {
      ...rejectedDoc,
      id: 4,
      reviewNote: "Older rejection — id unreadable",
      reviewedAt: "2026-01-05T10:00:00Z",
    };
    mockUseDocs.mockReturnValue({
      data: [olderRejected, rejectedDoc],
      isLoading: false,
    });
    renderKycCard();

    expect(screen.getByText(/Blurry scan — please re-upload/)).toBeInTheDocument();
    expect(screen.queryByText(/Older rejection/)).not.toBeInTheDocument();
  });

  it("handles a rejection with no note without dangling 'note below' copy", () => {
    mockUseDocs.mockReturnValue({ data: [emptyNoteRejectedDoc], isLoading: false });
    renderKycCard();

    expect(screen.queryByText("Why it was rejected")).not.toBeInTheDocument();
    expect(screen.getByText(/Upload a clear copy to try again/)).toBeInTheDocument();
    expect(screen.queryByText(/Review the note below/)).not.toBeInTheDocument();
  });

  it("shows the verified state even when an old rejected doc exists", () => {
    mockUseApp.mockReturnValue({ user: { role: "landlord", nidVerified: true } });
    mockUseDocs.mockReturnValue({ data: [rejectedDoc], isLoading: false });
    render(<KycCard />);

    expect(
      screen.getByText(
        "Verified — your listings carry the trust badge and rank above unverified landlords."
      )
    ).toBeInTheDocument();
    expect(screen.queryByText("Why it was rejected")).not.toBeInTheDocument();
  });

  it("uploads the chosen file with the selected document type", async () => {
    const mutateAsync = vi.fn().mockResolvedValue({});
    mockUseUpload.mockReturnValue({ mutateAsync, isPending: false });
    renderKycCard();

    const file = new File(["fake-doc"], "nid.jpg", { type: "image/jpeg" });
    await userEvent.upload(screen.getByLabelText("KYC document file"), file);
    await userEvent.click(screen.getByRole("button", { name: "Upload" }));

    expect(mutateAsync).toHaveBeenCalledWith({ docType: "nid", file });
  });
});
