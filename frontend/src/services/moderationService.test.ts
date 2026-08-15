import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./api", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

import { api } from "./api";
import { moderationService } from "./moderationService";

const apiReviewMod = {
  id: 11,
  review: 5,
  room_id: 7,
  room_title: "Sunlit Studio",
  author_username: "sabbir.rahman",
  author_name: "Sabbir Rahman",
  rating: 5,
  comment_preview: "Great! Contact me on whatsapp 01712345678",
  status: "pending",
  status_display: "Pending",
  risk_score: 80,
  signals: [{ key: "contact_info", label: "Contains phone number" }],
  admin_note: "",
  reviewed_by_username: "",
  created_at: "2026-01-05T10:00:00Z",
  reviewed_at: null,
};

const apiPhotoMod = {
  id: 21,
  target_type: "listing",
  target_type_display: "Listing",
  room: 7,
  room_title: "Sunlit Studio",
  review: null,
  image_url: "/media/rooms/abc.png",
  phash: "aabbccdd",
  status: "flagged",
  status_display: "Flagged",
  risk_score: 40,
  signals: [{ key: "duplicate_image", label: "Visually similar to another listing's photo" }],
  admin_note: "",
  uploaded_by_username: "rahim.hossain",
  reviewed_by_username: "",
  created_at: "2026-01-05T11:00:00Z",
  reviewed_at: null,
};

describe("moderationService (Phase 12.5)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("getOverview maps snake_case counts", async () => {
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { reviews: 3, reviews_pending: 2, reviews_approved: 1, photos: 1, photos_pending: 1 },
    });
    const overview = await moderationService.getOverview();
    expect(api.get).toHaveBeenCalledWith("/moderation/overview/");
    expect(overview).toMatchObject({
      reviews: 3,
      reviewsPending: 2,
      reviewsApproved: 1,
      photos: 1,
      photosPending: 1,
      photosFlagged: 0,
      reviewsRejected: 0,
    });
  });

  it("getReviews passes the status filter and maps items", async () => {
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: [apiReviewMod] });
    const items = await moderationService.getReviews("attention");
    expect(api.get).toHaveBeenCalledWith("/moderation/reviews/", {
      params: { status: "attention" },
    });
    expect(items[0]).toMatchObject({
      id: 11,
      review: 5,
      roomId: 7,
      roomTitle: "Sunlit Studio",
      rating: 5,
      commentPreview: "Great! Contact me on whatsapp 01712345678",
      status: "pending",
      statusDisplay: "Pending",
      riskScore: 80,
    });
  });

  it("decideReview posts the action and note", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { ...apiReviewMod, status: "approved", status_display: "Approved" },
    });
    const item = await moderationService.decideReview(11, "approve", "legit tenant");
    expect(api.post).toHaveBeenCalledWith("/moderation/reviews/11/decision/", {
      action: "approve",
      note: "legit tenant",
    });
    expect(item.status).toBe("approved");
  });

  it("getPhotos and decidePhoto hit the photo endpoints", async () => {
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: [apiPhotoMod] });
    const photos = await moderationService.getPhotos();
    expect(api.get).toHaveBeenCalledWith("/moderation/photos/", {
      params: { status: "attention" },
    });
    expect(photos[0].targetTypeDisplay).toBe("Listing");

    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { ...apiPhotoMod, status: "rejected", status_display: "Rejected" },
    });
    const decided = await moderationService.decidePhoto(21, "reject", "duplicate");
    expect(api.post).toHaveBeenCalledWith("/moderation/photos/21/decision/", {
      action: "reject",
      note: "duplicate",
    });
    expect(decided.status).toBe("rejected");
  });
});
