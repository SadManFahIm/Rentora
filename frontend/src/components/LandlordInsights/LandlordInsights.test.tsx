import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import LandlordInsights from "./LandlordInsights";
import roomService from "../../services/roomService";

vi.mock("../../services/roomService", () => ({
  default: { getInsights: vi.fn() },
}));

const insights = {
  rooms: [
    {
      id: 1,
      title: "Sunny Studio",
      price: 12000,
      area: "Dhanmondi",
      roomType: "studio",
      tier: "free",
      verified: true,
      views7d: 4,
      views30d: 18,
      viewsTotal: 40,
      wishlistCount: 3,
      bookingRequests: 2,
      bookingApproved: 1,
      areaAvgPrice: 15000,
      priceDeltaPct: -20,
    },
  ],
  summary: { listingCount: 1, totalViews30d: 18, totalWishlists: 3 },
};

function renderInsights() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <LandlordInsights />
    </QueryClientProvider>
  );
}

describe("LandlordInsights", () => {
  it("renders summary cards and the per-listing table", async () => {
    vi.mocked(roomService.getInsights).mockResolvedValue(insights);
    renderInsights();

    expect(await screen.findByText("18")).toBeInTheDocument();
    expect(screen.getByText("Sunny Studio")).toBeInTheDocument();
    expect(screen.getByText("4 / 18")).toBeInTheDocument();
    expect(screen.getByText("1 approved")).toBeInTheDocument();
    // Price is 20% below the ৳15,000 area average → "−20% vs ৳15,000"
    expect(screen.getByText(/-20% vs ৳15,000/)).toBeInTheDocument();
  });
});
