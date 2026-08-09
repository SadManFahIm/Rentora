/**
 * Component test: the fraud "Under review" badge inside RoomModal.
 *
 * The badge is gated on the live fraud status (useRoomFraudStatus), so the
 * hook is mocked and we assert what the user actually sees for each
 * severity: HIGH → "Under review (high risk)", clean → no badge at all.
 * Complements the store/service integration test in services/fraudFlow.test.ts.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Room } from "../../types";
import RoomModal from "./RoomModal";

vi.mock("react-router-dom", () => ({
  useNavigate: () => vi.fn(),
}));

vi.mock("sonner", () => ({
  toast: { info: vi.fn(), error: vi.fn(), success: vi.fn() },
}));

vi.mock("../../hooks/useFraud", () => ({
  useRoomFraudStatus: vi.fn(),
}));

vi.mock("../../hooks/useBookings", () => ({
  useCreateBooking: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock("../../hooks/useChat", () => ({
  useStartDirectChat: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock("../../context/AppContext", () => ({
  useApp: () => ({ user: null }),
}));

vi.mock("../../services/api", () => ({
  isAuthenticated: () => false,
}));

vi.mock("../../services/errors", () => ({
  getApiErrorMessage: () => "error",
}));

import { useRoomFraudStatus } from "../../hooks/useFraud";

const mockUseRoomFraudStatus = useRoomFraudStatus as ReturnType<typeof vi.fn>;

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
  amenities: ["WiFi", "AC"],
  gender: "Any",
  available: true,
  featured: false,
  tier: "free",
  tierExpiresAt: null,
  description: "Bright studio near the metro.",
  size: 420,
  owner: "Landlord",
  ownerId: 1,
  ownerAvatar: "L",
  verified: true,
};

function fraudStatus(severity: "clean" | "low" | "medium" | "high", score = 0) {
  return { roomId: 18, severity, score, flagged: severity !== "clean", message: "x" };
}

describe("RoomModal fraud badge", () => {
  it("renders the red risk badge when the room is flagged HIGH", () => {
    mockUseRoomFraudStatus.mockReturnValue({ data: fraudStatus("high", 100) });
    render(<RoomModal room={room} onClose={vi.fn()} />);

    expect(screen.getByText("Under review (high risk)")).toBeInTheDocument();
  });

  it("renders the medium-risk badge for a MEDIUM flag", () => {
    mockUseRoomFraudStatus.mockReturnValue({ data: fraudStatus("medium", 60) });
    render(<RoomModal room={room} onClose={vi.fn()} />);

    expect(screen.getByText("Under review (medium risk)")).toBeInTheDocument();
  });

  it("renders the bare badge for an informational LOW flag", () => {
    mockUseRoomFraudStatus.mockReturnValue({ data: fraudStatus("low", 25) });
    render(<RoomModal room={room} onClose={vi.fn()} />);

    expect(screen.getByText("Under review")).toBeInTheDocument();
  });

  it("renders no badge when the room is clean", () => {
    mockUseRoomFraudStatus.mockReturnValue({ data: fraudStatus("clean") });
    render(<RoomModal room={room} onClose={vi.fn()} />);

    expect(screen.queryByText(/Under review/)).not.toBeInTheDocument();
  });

  it("renders no badge while the fraud status is still loading", () => {
    mockUseRoomFraudStatus.mockReturnValue({ data: undefined });
    render(<RoomModal room={room} onClose={vi.fn()} />);

    expect(screen.queryByText(/Under review/)).not.toBeInTheDocument();
  });
});
