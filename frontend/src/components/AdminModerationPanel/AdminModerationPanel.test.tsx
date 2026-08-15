/**
 * Component test for the Phase 12.5 content moderation panel: overview
 * counts, the review/photo queue switcher, and audited approve/reject
 * decisions. Hooks are mocked; rendering + action wiring are under test.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AdminModerationPanel from "./AdminModerationPanel";

vi.mock("../../hooks/useModeration", () => ({
  useModerationOverview: vi.fn(),
  useReviewModerationQueue: vi.fn(),
  usePhotoModerationQueue: vi.fn(),
  useDecideReviewModeration: vi.fn(),
  useDecidePhotoModeration: vi.fn(),
}));

import {
  useDecidePhotoModeration,
  useDecideReviewModeration,
  useModerationOverview,
  usePhotoModerationQueue,
  useReviewModerationQueue,
} from "../../hooks/useModeration";

const mockOverview = useModerationOverview as ReturnType<typeof vi.fn>;
const mockReviews = useReviewModerationQueue as ReturnType<typeof vi.fn>;
const mockPhotos = usePhotoModerationQueue as ReturnType<typeof vi.fn>;
const mockDecideReview = useDecideReviewModeration as ReturnType<typeof vi.fn>;
const mockDecidePhoto = useDecidePhotoModeration as ReturnType<typeof vi.fn>;

const pendingReview = {
  id: 11,
  review: 5,
  roomId: 7,
  roomTitle: "Sunlit Studio",
  authorUsername: "sabbir.rahman",
  authorName: "Sabbir Rahman",
  rating: 5,
  commentPreview: "Great! Contact me on whatsapp 01712345678",
  status: "pending",
  statusDisplay: "Pending",
  riskScore: 80,
  signals: [{ key: "contact_info", label: "Contains phone number" }],
  adminNote: "",
  reviewedByUsername: "",
  createdAt: "2026-01-05T10:00:00Z",
  reviewedAt: null,
};

const flaggedPhoto = {
  id: 21,
  targetType: "listing",
  targetTypeDisplay: "Listing",
  room: 7,
  roomTitle: "Sunlit Studio",
  review: null,
  imageUrl: "/media/rooms/abc.png",
  phash: "aabbccdd",
  status: "flagged",
  statusDisplay: "Flagged",
  riskScore: 40,
  signals: [{ key: "duplicate_image", label: "Visually similar to another listing's photo" }],
  adminNote: "",
  uploadedByUsername: "rahim.hossain",
  reviewedByUsername: "",
  createdAt: "2026-01-05T11:00:00Z",
  reviewedAt: null,
};

function renderPanel() {
  return render(<AdminModerationPanel />);
}

describe("AdminModerationPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockOverview.mockReturnValue({ data: undefined, isLoading: false });
    mockReviews.mockReturnValue({ data: [], isLoading: false });
    mockPhotos.mockReturnValue({ data: [], isLoading: false });
    mockDecideReview.mockReturnValue({ isPending: false, variables: null, mutateAsync: vi.fn() });
    mockDecidePhoto.mockReturnValue({ isPending: false, variables: null, mutateAsync: vi.fn() });
  });

  it("shows overview counts and an empty state by default", () => {
    mockOverview.mockReturnValue({
      data: {
        reviews: 3,
        reviewsPending: 2,
        reviewsFlagged: 0,
        reviewsApproved: 1,
        reviewsRejected: 0,
        photos: 1,
        photosPending: 0,
        photosFlagged: 1,
        photosApproved: 0,
        photosRejected: 0,
      },
      isLoading: false,
    });
    renderPanel();
    expect(screen.getByText("Content Moderation")).toBeInTheDocument();
    expect(screen.getByText("Reviews pending")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText(/this queue is clear/i)).toBeInTheDocument();
  });

  it("lists a pending review with signals and approves it with a note", async () => {
    mockReviews.mockReturnValue({ data: [pendingReview], isLoading: false });
    const mutateAsync = vi.fn().mockResolvedValue({});
    mockDecideReview.mockReturnValue({ isPending: false, variables: null, mutateAsync });
    renderPanel();

    expect(screen.getByText(/5★ review on Sunlit Studio/)).toBeInTheDocument();
    expect(screen.getByText(/by Sabbir Rahman/)).toBeInTheDocument();
    expect(screen.getByText("Contains phone number")).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("Note for item 11"), "legit tenant");
    await userEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(mutateAsync).toHaveBeenCalledWith({
      id: 11,
      action: "approve",
      note: "legit tenant",
    });
  });

  it("switches to the photo queue and rejects a flagged photo", async () => {
    mockPhotos.mockReturnValue({ data: [flaggedPhoto], isLoading: false });
    const mutateAsync = vi.fn().mockResolvedValue({});
    mockDecidePhoto.mockReturnValue({ isPending: false, variables: null, mutateAsync });
    renderPanel();

    await userEvent.click(screen.getByRole("button", { name: /photos/i }));
    expect(screen.getByText(/Listing photo for Sunlit Studio/)).toBeInTheDocument();
    expect(screen.getByText("Visually similar to another listing's photo")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Reject" }));
    expect(mutateAsync).toHaveBeenCalledWith({ id: 21, action: "reject", note: "" });
  });
});
