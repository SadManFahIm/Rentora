import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import ReviewsSection from "./ReviewsSection";
import reviewService from "../../services/reviewService";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("../../services/errors", () => ({ getApiErrorMessage: () => "error" }));

vi.mock("../../services/reviewService", () => ({
  default: {
    getSummary: vi.fn(),
    replyToReview: vi.fn(),
  },
}));

const summary = {
  room: 1,
  averageRating: 4.5,
  totalReviews: 2,
  countsPerStar: { "1": 0, "2": 0, "3": 1, "4": 0, "5": 1 },
  recent: [
    {
      id: 11,
      room: 1,
      user: { id: 2, username: "tenant", firstName: "Tanvir", avatar: null },
      rating: 5,
      comment: "Great stay",
      verifiedStay: true,
      photos: [],
      reply: "",
      repliedAt: null,
      createdAt: "2026-08-01T00:00:00Z",
    },
    {
      id: 12,
      room: 1,
      user: { id: 3, username: "other", firstName: "", avatar: null },
      rating: 3,
      comment: "Okay room",
      verifiedStay: false,
      photos: [],
      reply: "Thanks for the feedback!",
      repliedAt: "2026-08-02T00:00:00Z",
      createdAt: "2026-08-01T12:00:00Z",
    },
  ],
};

function renderSection(props: { isOwner: boolean }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ReviewsSection roomId={1} isOwner={props.isOwner} />
    </QueryClientProvider>
  );
}

describe("ReviewsSection", () => {
  it("renders the rating breakdown and recent reviews", async () => {
    vi.mocked(reviewService.getSummary).mockResolvedValue(summary);
    renderSection({ isOwner: false });

    expect(await screen.findByText(/Reviews \(2\)/)).toBeInTheDocument();
    expect(screen.getByText("4.5")).toBeInTheDocument();
    expect(screen.getByText("Great stay")).toBeInTheDocument();
    expect(screen.getByText("Verified stay")).toBeInTheDocument();
    expect(screen.getByText("Landlord response")).toBeInTheDocument();
    expect(screen.getByText("Thanks for the feedback!")).toBeInTheDocument();
  });

  it("shows the reply form only for the room owner", async () => {
    vi.mocked(reviewService.getSummary).mockResolvedValue(summary);
    renderSection({ isOwner: true });
    expect(await screen.findByText(/Reviews \(2\)/)).toBeInTheDocument();
    expect(screen.getAllByPlaceholderText(/Reply to this review/).length).toBeGreaterThan(0);
  });
});
