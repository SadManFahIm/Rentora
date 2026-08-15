import { api } from "./api";
import {
  mapModerationOverview,
  mapPhotoModeration,
  mapReviewModeration,
  type ApiPhotoModeration,
  type ApiReviewModeration,
} from "./mappers";
import type {
  ModerationOverview,
  ModerationStatus,
  PhotoModerationItem,
  ReviewModerationItem,
} from "../types";

// ============================================================
// MODERATION SERVICE — Phase 12.5 content moderation queue
// (admin-only endpoints; the server enforces staff/admin access).
// ============================================================

export const moderationService = {
  /** GET /moderation/overview/ — queue-health counts (admin). */
  async getOverview(): Promise<ModerationOverview> {
    const { data } = await api.get<Record<string, number>>("/moderation/overview/");
    return mapModerationOverview(data);
  },

  /** GET /moderation/reviews/ — review moderation queue (admin).
   * `status`: attention (default) | pending | flagged | approved | rejected | all. */
  async getReviews(status = "attention"): Promise<ReviewModerationItem[]> {
    const { data } = await api.get<ApiReviewModeration[]>("/moderation/reviews/", {
      params: { status },
    });
    return data.map(mapReviewModeration);
  },

  /** POST /moderation/reviews/:id/decision/ — approve | reject (admin). */
  async decideReview(
    id: number,
    action: "approve" | "reject",
    note = ""
  ): Promise<ReviewModerationItem> {
    const { data } = await api.post<ApiReviewModeration>(`/moderation/reviews/${id}/decision/`, {
      action,
      note,
    });
    return mapReviewModeration(data);
  },

  /** GET /moderation/photos/ — photo moderation queue (admin). */
  async getPhotos(status = "attention"): Promise<PhotoModerationItem[]> {
    const { data } = await api.get<ApiPhotoModeration[]>("/moderation/photos/", {
      params: { status },
    });
    return data.map(mapPhotoModeration);
  },

  /** POST /moderation/photos/:id/decision/ — approve | reject (admin). */
  async decidePhoto(
    id: number,
    action: "approve" | "reject",
    note = ""
  ): Promise<PhotoModerationItem> {
    const { data } = await api.post<ApiPhotoModeration>(`/moderation/photos/${id}/decision/`, {
      action,
      note,
    });
    return mapPhotoModeration(data);
  },
};

/** Statuses that still need an admin's attention. */
export const MODERATION_ATTENTION_STATUSES: ModerationStatus[] = ["pending", "flagged"];

export default moderationService;
