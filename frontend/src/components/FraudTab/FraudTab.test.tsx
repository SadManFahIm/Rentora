/**
 * Component test for the dashboard's fraud tab (report cards + actions).
 * Hooks are mocked; the rendering + admin/landlord permission split and the
 * Re-scan / Mark reviewed / Dismiss actions are what's under test.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { FraudReport, Room } from "../../types";
import FraudTab from "./FraudTab";

vi.mock("../../hooks/useFraud", () => ({
  useFraudReports: vi.fn(),
  useScanRoom: vi.fn(),
  useReviewFraudReport: vi.fn(),
}));

vi.mock("../../context/AppContext", () => ({
  useApp: vi.fn(),
}));

import { useApp } from "../../context/AppContext";
import { useFraudReports, useReviewFraudReport, useScanRoom } from "../../hooks/useFraud";

const mockUseFraudReports = useFraudReports as ReturnType<typeof vi.fn>;
const mockUseScanRoom = useScanRoom as ReturnType<typeof vi.fn>;
const mockUseReview = useReviewFraudReport as ReturnType<typeof vi.fn>;
const mockUseApp = useApp as ReturnType<typeof vi.fn>;

const room: Room = {
  id: 18,
  name: "Modern Studio, Mirpur",
  type: "Studio",
  price: 13500,
  area: "Mirpur",
  lat: 23.81,
  lng: 90.37,
  rating: 4.6,
  reviews: 15,
  img: "https://example.com/room.jpg",
  amenities: ["WiFi"],
  gender: "Any",
  available: true,
  featured: false,
  tier: "free",
  tierExpiresAt: null,
  description: "Bright studio.",
  size: 420,
  owner: "Landlord",
  ownerId: 1,
  ownerAvatar: "L",
  verified: false,
};

const report: FraudReport = {
  id: 4,
  room,
  severity: "high",
  severityDisplay: "High",
  status: "open",
  statusDisplay: "Open",
  score: 100,
  summary: "Risk score 100/100. Signals: Duplicate Listing.",
  signals: [
    {
      id: 1,
      detector: "duplicate_listing",
      detectorDisplay: "Duplicate Listing",
      severity: "high",
      message: "Title is 100% similar to listing #7.",
      detail: { similar_room_id: 7 },
      createdAt: "2025-01-05T10:00:00Z",
    },
  ],
  createdAt: "2025-01-05T10:00:00Z",
  updatedAt: "2025-01-05T10:00:00Z",
};

function mutationMock() {
  return { mutate: vi.fn(), isPending: false, variables: undefined };
}

function renderFraudTab(role: "landlord" | "admin" = "landlord") {
  mockUseApp.mockReturnValue({ user: { role } });
  return render(<FraudTab />);
}

describe("FraudTab", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseScanRoom.mockReturnValue(mutationMock());
    mockUseReview.mockReturnValue(mutationMock());
  });

  it("renders a flagged report card with severity and signal detail", () => {
    mockUseFraudReports.mockReturnValue({ data: [report], isLoading: false });
    renderFraudTab();

    expect(screen.getByText("Modern Studio, Mirpur")).toBeInTheDocument();
    expect(screen.getByText("High risk · 100/100")).toBeInTheDocument();
    expect(screen.getByText("Duplicate Listing:")).toBeInTheDocument();
    expect(screen.getByText("Title is 100% similar to listing #7.")).toBeInTheDocument();
  });

  it("re-scan calls the mutation with the room id", async () => {
    const scan = mutationMock();
    mockUseScanRoom.mockReturnValue(scan);
    mockUseFraudReports.mockReturnValue({ data: [report], isLoading: false });
    renderFraudTab();

    await userEvent.click(screen.getByRole("button", { name: "Re-scan" }));
    expect(scan.mutate).toHaveBeenCalledWith(18);
  });

  it("hides review actions for a non-admin landlord", () => {
    mockUseFraudReports.mockReturnValue({ data: [report], isLoading: false });
    const { unmount } = renderFraudTab("landlord");

    expect(screen.queryByRole("button", { name: "Mark reviewed" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Dismiss" })).not.toBeInTheDocument();
    unmount();
  });

  it("shows review actions to an admin and dispatches the review", async () => {
    const review = mutationMock();
    mockUseReview.mockReturnValue(review);
    mockUseFraudReports.mockReturnValue({ data: [report], isLoading: false });
    renderFraudTab("admin");

    await userEvent.click(screen.getByRole("button", { name: "Mark reviewed" }));
    expect(review.mutate).toHaveBeenCalledWith({ reportId: 4, action: "reviewed" });
  });

  it("hides review buttons once a report is reviewed", () => {
    mockUseFraudReports.mockReturnValue({
      data: [{ ...report, status: "reviewed", statusDisplay: "Reviewed" }],
      isLoading: false,
    });
    renderFraudTab("admin");

    expect(screen.getByText("Reviewed")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark reviewed" })).not.toBeInTheDocument();
  });

  it("renders the empty state when there are no reports", () => {
    mockUseFraudReports.mockReturnValue({ data: [], isLoading: false });
    renderFraudTab();

    expect(screen.getByText("No flagged listings")).toBeInTheDocument();
  });

  it("renders the loading state while reports are fetched", () => {
    mockUseFraudReports.mockReturnValue({ data: [], isLoading: true });
    renderFraudTab();

    expect(screen.getByText("Loading fraud reports…")).toBeInTheDocument();
  });
});
