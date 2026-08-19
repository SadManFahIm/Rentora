import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi, beforeEach } from "vitest";
import VisionCard from "./VisionCard";
vi.mock("sonner", () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

import { toast } from "sonner";
import roomService from "../../services/roomService";
import type { Room } from "../../types";

vi.mock("../../services/roomService", () => ({
  default: { updateRoom: vi.fn() },
}));

const analyzeMock = vi.fn();
const draftMock = vi.fn();

vi.mock("../../hooks/useVision", () => ({
  useVisionAnalyze: () => ({
    isPending: false,
    mutateAsync: analyzeMock,
  }),
  useVisionDescription: () => ({
    isPending: false,
    mutateAsync: draftMock,
  }),
}));

const room: Room = {
  id: 7,
  name: "Sunny Studio",
  type: "Studio",
  price: 12000,
  area: "Dhanmondi",
  lat: 23.74,
  lng: 90.37,
  amenities: ["WiFi"],
  verified: true,
  tier: "free",
  rating: 4.5,
  reviews: 12,
  owner: "Fahim",
  ownerId: 1,
  ownerAvatar: "F",
  img: "/room.jpg",
  available: true,
  featured: false,
  tierExpiresAt: null,
  description: "",
  size: 280,
  gender: "Any",
};

const analysis = {
  available: true,
  provider: "heuristic",
  caption: "A bright, airy studio with a calm light-tone palette.",
  observations: [
    { kind: "lighting", label: "Well-lit space", confidence: 0.9 },
    { kind: "tone", label: "Light-tone interiors", confidence: 0.8 },
  ],
  suggested_amenities: ["Furnished"],
  palette: [{ hex: "#f2f0e8", name: "Ivory", share: 0.34 }],
  photo_count: 1,
  note: "Photo intelligence is statistical.",
};

function renderCard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <VisionCard room={room} />
    </QueryClientProvider>
  );
}

describe("VisionCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    analyzeMock.mockReset();
    draftMock.mockReset();
  });

  it("analyzes the listing photos and shows observations, palette and note", async () => {
    analyzeMock.mockResolvedValue(analysis);
    renderCard();

    fireEvent.click(screen.getByRole("button", { name: /analyze photos/i }));

    expect(await screen.findByText(/bright, airy studio/i)).toBeInTheDocument();
    expect(screen.getByText("Ivory")).toBeInTheDocument();
    expect(screen.getByText("Well-lit space")).toBeInTheDocument();
    expect(screen.getByText(/photo intelligence is statistical/i)).toBeInTheDocument();
  });

  it("shows an error toast when no photos are available", async () => {
    analyzeMock.mockResolvedValue({
      ...analysis,
      available: false,
      reason: "No photos to analyze.",
    });
    renderCard();

    fireEvent.click(screen.getByRole("button", { name: /analyze photos/i }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("No photos to analyze."));
  });

  it("applies suggested tags to the listing", async () => {
    analyzeMock.mockResolvedValue(analysis);
    (roomService.updateRoom as ReturnType<typeof vi.fn>).mockResolvedValue({});
    renderCard();

    fireEvent.click(screen.getByRole("button", { name: /analyze photos/i }));
    fireEvent.click(await screen.findByRole("button", { name: /apply tags/i }));

    await waitFor(() =>
      expect(roomService.updateRoom).toHaveBeenCalledWith(7, {
        amenities: ["WiFi", "Furnished"],
      })
    );
  });

  it("generates an AI draft from the photos", async () => {
    draftMock.mockResolvedValue({
      title: "Bright Studio in Dhanmondi",
      description: "A well-lit studio close to campus.",
      amenities: ["Furnished"],
      observations: [],
      note: "Draft from the listing's photos.",
    });
    renderCard();

    fireEvent.click(screen.getByRole("button", { name: /ai draft from photos/i }));

    expect(await screen.findByText("Bright Studio in Dhanmondi")).toBeInTheDocument();
    expect(screen.getByText(/well-lit studio close to campus/i)).toBeInTheDocument();
  });
});
