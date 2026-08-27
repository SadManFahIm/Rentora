import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import RoomCard from "./RoomCard";
import type { Room } from "../../types";

function makeRoom(overrides: Partial<Room> = {}): Room {
  return {
    id: 1,
    name: "Sunny Studio in Dhanmondi",
    type: "Studio",
    price: 12000,
    area: "Dhanmondi",
    lat: 23.746,
    lng: 90.376,
    rating: 4.5,
    reviews: 12,
    img: "https://example.com/room.jpg",
    amenities: ["WiFi", "AC", "Attached Bath", "Furnished"],
    gender: "Any",
    available: true,
    featured: false,
    tier: "free",
    tierExpiresAt: null,
    description: "A sunny studio apartment",
    size: 300,
    owner: "Rahim",
    ownerId: 2,
    ownerAvatar: "R",
    verified: false,
    ...overrides,
  };
}

describe("RoomCard", () => {
  it("renders room name and price", () => {
    const room = makeRoom();
    render(<RoomCard room={room} onClick={vi.fn()} />);
    expect(screen.getByText("Sunny Studio in Dhanmondi")).toBeInTheDocument();
    expect(screen.getByText(/৳12,000/)).toBeInTheDocument();
  });

  it("renders room area and type", () => {
    const room = makeRoom();
    render(<RoomCard room={room} onClick={vi.fn()} />);
    expect(screen.getByText("Dhanmondi")).toBeInTheDocument();
    const studioMatches = screen.getAllByText("Studio");
    expect(studioMatches.length).toBeGreaterThanOrEqual(1);
  });

  it("renders rating and review count", () => {
    const room = makeRoom();
    render(<RoomCard room={room} onClick={vi.fn()} />);
    expect(screen.getByText("4.5")).toBeInTheDocument();
    expect(screen.getByText("(12)")).toBeInTheDocument();
  });

  it("calls onClick when card is clicked", () => {
    const room = makeRoom();
    const onClick = vi.fn();
    render(<RoomCard room={room} onClick={onClick} />);
    fireEvent.click(screen.getByText("Sunny Studio in Dhanmondi"));
    expect(onClick).toHaveBeenCalledWith(room);
  });

  it("shows available badge for available rooms", () => {
    const room = makeRoom({ available: true });
    render(<RoomCard room={room} onClick={vi.fn()} />);
    const matches = screen.getAllByText("Studio");
    expect(matches.length).toBeGreaterThanOrEqual(1);
  });

  it("shows unavailable badge for unavailable rooms", () => {
    const room = makeRoom({ available: false });
    render(<RoomCard room={room} onClick={vi.fn()} />);
    const matches = screen.getAllByText(/unavailable/i);
    expect(matches.length).toBeGreaterThanOrEqual(1);
  });

  it("shows verified badge when owner is verified", () => {
    const room = makeRoom({ verified: true });
    render(<RoomCard room={room} onClick={vi.fn()} />);
    expect(screen.getByText("Verified")).toBeInTheDocument();
  });

  it("does not show verified badge when owner is not verified", () => {
    const room = makeRoom({ verified: false });
    render(<RoomCard room={room} onClick={vi.fn()} />);
    expect(screen.queryByText("Verified")).not.toBeInTheDocument();
  });

  it("renders first 3 amenities", () => {
    const room = makeRoom({ amenities: ["WiFi", "AC", "Attached Bath", "Furnished", "Gym"] });
    render(<RoomCard room={room} onClick={vi.fn()} />);
    expect(screen.getByText("WiFi")).toBeInTheDocument();
    expect(screen.getByText("AC")).toBeInTheDocument();
    expect(screen.getByText("Attached Bath")).toBeInTheDocument();
    expect(screen.getByText("+2")).toBeInTheDocument();
  });

  it("shows match info when provided", () => {
    const room = makeRoom();
    const matchInfo = { score: 85, reasons: ["Similar price", "Same area"] };
    render(<RoomCard room={room} onClick={vi.fn()} matchInfo={matchInfo} />);
    expect(screen.getByText(/85%/)).toBeInTheDocument();
  });

  it("applies premium tier styling", () => {
    const room = makeRoom({ tier: "premium" });
    const { container } = render(<RoomCard room={room} onClick={vi.fn()} />);
    const card = container.querySelector("[class*='ring-amber']");
    expect(card).toBeInTheDocument();
  });

  it("applies featured tier styling", () => {
    const room = makeRoom({ tier: "featured" });
    const { container } = render(<RoomCard room={room} onClick={vi.fn()} />);
    const card = container.querySelector("[class*='border-orange-300']");
    expect(card).toBeInTheDocument();
  });
});
