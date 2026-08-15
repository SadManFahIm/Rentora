import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { moderationService } from "../services/moderationService";
import type { ModerationOverview, PhotoModerationItem, ReviewModerationItem } from "../types";

export const moderationKeys = {
  all: ["moderation"] as const,
  overview: () => [...moderationKeys.all, "overview"] as const,
  reviews: (status: string) => [...moderationKeys.all, "reviews", status] as const,
  photos: (status: string) => [...moderationKeys.all, "photos", status] as const,
};

export function useModerationOverview() {
  return useQuery<ModerationOverview>({
    queryKey: moderationKeys.overview(),
    queryFn: () => moderationService.getOverview(),
  });
}

export function useReviewModerationQueue(status = "attention") {
  return useQuery<ReviewModerationItem[]>({
    queryKey: moderationKeys.reviews(status),
    queryFn: () => moderationService.getReviews(status),
  });
}

export function usePhotoModerationQueue(status = "attention") {
  return useQuery<PhotoModerationItem[]>({
    queryKey: moderationKeys.photos(status),
    queryFn: () => moderationService.getPhotos(status),
  });
}

export function useDecideReviewModeration() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      action,
      note,
    }: {
      id: number;
      action: "approve" | "reject";
      note?: string;
    }) => moderationService.decideReview(id, action, note),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: moderationKeys.all });
    },
  });
}

export function useDecidePhotoModeration() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      action,
      note,
    }: {
      id: number;
      action: "approve" | "reject";
      note?: string;
    }) => moderationService.decidePhoto(id, action, note),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: moderationKeys.all });
    },
  });
}
