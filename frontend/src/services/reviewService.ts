import { api } from "./api";
import type { ReviewItem, ReviewSummary } from "../types";

// ============================================================
// REVIEW SERVICE — summary + landlord reply (Reviews v2)
// ============================================================

interface ApiReviewSummary {
  room: number;
  average_rating: number;
  total_reviews: number;
  counts_per_star: Record<"1" | "2" | "3" | "4" | "5", number>;
  recent: ApiReviewItem[];
}

interface ApiReviewItem {
  id: number;
  room: number;
  user: { id: number; username: string; first_name: string; avatar: string | null };
  rating: number;
  comment: string;
  verified_stay: boolean;
  photos: string[];
  reply: string;
  replied_at: string | null;
  created_at: string;
}

function mapReviewItem(item: ApiReviewItem): ReviewItem {
  return {
    id: item.id,
    room: item.room,
    user: {
      id: item.user.id,
      username: item.user.username,
      firstName: item.user.first_name,
      avatar: item.user.avatar,
    },
    rating: item.rating,
    comment: item.comment,
    verifiedStay: item.verified_stay,
    photos: item.photos ?? [],
    reply: item.reply ?? "",
    repliedAt: item.replied_at,
    createdAt: item.created_at,
  };
}

export const reviewService = {
  async getSummary(roomId: number): Promise<ReviewSummary> {
    const { data } = await api.get<ApiReviewSummary>(`/reviews/summary/?room=${roomId}`);
    return {
      room: data.room,
      averageRating: data.average_rating,
      totalReviews: data.total_reviews,
      countsPerStar: data.counts_per_star,
      recent: data.recent.map(mapReviewItem),
    };
  },

  async replyToReview(reviewId: number, reply: string): Promise<void> {
    await api.post<{ status: string }>(`/reviews/${reviewId}/reply/`, { reply });
  },
};

export default reviewService;
