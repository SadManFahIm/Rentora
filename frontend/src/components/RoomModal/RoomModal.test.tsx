import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import RoomModal from "./RoomModal";
import type { Room } from "../../types";

// Mock the hooks that RoomModal uses
vi.mock("../../hooks/useFraud", () => ({
  useRoomFraudStatus: () => ({ data: null }),
}));

vi.mock("../../hooks/useBookings", () => ({
  useCreateBooking: () => ({
    mutate: vi.fn(),
    isPending: false,
  }),
}));

vi.mock("../../hooks/useChat", () => ({
  useStartDirectChat: () => ({
    mutate: vi.fn(),
    isPending: false,
  }),
}));

vi.mock("../../hooks/useListingShare", () => ({
  useListingShare: () => ({
    share: vi.fn(),
    sharingId: null,
  }),
}));

vi.mock("../../context/AppContext", () => ({
  useApp: () => ({ user: null }),
}));

vi.mock("../../services/api", () => ({
  isAuthenticated: () => false,
}));

vi.mock("../../stores/copilotStore", () => ({
  useCopilotStore: {
    getState: () => ({
      openWithListing: vi.fn(),
      requestAiTool: vi.fn(),
    }),
  },
}));

vi.mock("../../services/analytics", () => ({
  track: vi.fn(),
}));

vi.mock("../../lib/fraud", () => ({
  fraudBadgeLabel: () => "Low Risk",
}));

function makeRoom(overrides: Partial<Room> = {}): Room {
  return {
    id: 1,
    name: "Sunny Studio",
    type: "Studio",
    price: 12000,
    area: "Dhanmondi",
    lat: 23.746,
    lng: 90.376,
    rating: 4.5,
    reviews: 12,
    img: "https://example.com/room.jpg",
    amenities: ["WiFi", "AC"],
    gender: "Any",
    available: true,
    featured: false,
    tier: "free",
    tierExpiresAt: null,
    description: "A sunny studio apartment in the heart of Dhanmondi.",
    size: 300,
    owner: "Rahim",
    ownerId: 2,
    ownerAvatar: "R",
    verified: true,
    ...overrides,
  };
}

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

function renderWithRouter(ui: React.ReactElement) {
  return render(
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>{ui}</BrowserRouter>
    </QueryClientProvider>
  );
}

describe("RoomModal", () => {
  it("does not render dialog when room is null", () => {
    const { container } = renderWithRouter(<RoomModal room={null} onClose={vi.fn()} />);
    expect(container.querySelector('[role="dialog"]')).toBeNull();
  });

  it("renders dialog when room is provided", () => {
    const room = makeRoom();
    renderWithRouter(<RoomModal room={room} onClose={vi.fn()} />);
    // Radix Dialog renders a dialog role element
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("renders room name in dialog", () => {
    const room = makeRoom();
    renderWithRouter(<RoomModal room={room} onClose={vi.fn()} />);
    const matches = screen.getAllByText("Sunny Studio");
    expect(matches.length).toBeGreaterThanOrEqual(1);
  });

  it("renders Book Now button", () => {
    const room = makeRoom();
    renderWithRouter(<RoomModal room={room} onClose={vi.fn()} />);
    expect(screen.getByText("Book Now")).toBeInTheDocument();
  });

  it("renders Message Owner button", () => {
    const room = makeRoom();
    renderWithRouter(<RoomModal room={room} onClose={vi.fn()} />);
    expect(screen.getByText("Message Owner")).toBeInTheDocument();
  });

  it("renders owner name", () => {
    const room = makeRoom();
    renderWithRouter(<RoomModal room={room} onClose={vi.fn()} />);
    expect(screen.getByText("Rahim")).toBeInTheDocument();
  });
});
