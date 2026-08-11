import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MessageSquareReply, Star } from "lucide-react";
import { toast } from "sonner";
import { Button } from "../ui/button";
import reviewService from "../../services/reviewService";
import { getApiErrorMessage } from "../../services/errors";
import { cn } from "../../lib/utils";

interface ReviewsSectionProps {
  roomId: number;
  /** True when the viewer owns the room — shows the landlord reply form. */
  isOwner: boolean;
}

const STARS = [5, 4, 3, 2, 1] as const;

/** Rating breakdown + recent reviews with landlord replies (Reviews v2). */
export default function ReviewsSection({ roomId, isOwner }: ReviewsSectionProps) {
  const queryClient = useQueryClient();
  const [replyText, setReplyText] = useState<Record<number, string>>({});

  const { data: summary, isLoading } = useQuery({
    queryKey: ["review-summary", roomId],
    queryFn: () => reviewService.getSummary(roomId),
    enabled: !!roomId,
  });

  const replyMutation = useMutation({
    mutationFn: ({ reviewId, reply }: { reviewId: number; reply: string }) =>
      reviewService.replyToReview(reviewId, reply),
    onSuccess: () => {
      toast.success("Reply posted");
      queryClient.invalidateQueries({ queryKey: ["review-summary", roomId] });
    },
    onError: (error) => toast.error(getApiErrorMessage(error, "Could not post reply.")),
  });

  if (isLoading) return null;
  if (!summary || summary.totalReviews === 0) return null;

  const maxCount = Math.max(1, ...STARS.map((s) => summary.countsPerStar[String(s) as "1"] ?? 0));

  return (
    <div className="mt-8 border-t pt-6">
      <h3 className="mb-4 font-display text-lg font-bold text-foreground">
        Reviews ({summary.totalReviews})
      </h3>

      {/* Rating breakdown */}
      <div className="mb-6 flex flex-col gap-4 rounded-xl bg-gray-50 p-4 sm:flex-row sm:items-center dark:bg-gray-800">
        <div className="text-center">
          <div className="font-display text-4xl font-bold text-foreground">
            {summary.averageRating}
          </div>
          <div className="flex justify-center gap-0.5 text-amber-500">
            {[1, 2, 3, 4, 5].map((n) => (
              <Star
                key={n}
                className={cn("size-4", n <= Math.round(summary.averageRating) && "fill-amber-500")}
              />
            ))}
          </div>
        </div>
        <div className="flex-1 space-y-1">
          {STARS.map((star) => {
            const count = summary.countsPerStar[String(star) as "1"] ?? 0;
            return (
              <div key={star} className="flex items-center gap-2 text-xs">
                <span className="w-6 text-gray-600 dark:text-gray-400">{star}★</span>
                <div className="h-2 flex-1 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
                  <div
                    className="h-full rounded-full bg-amber-500"
                    style={{ width: `${(count / maxCount) * 100}%` }}
                  />
                </div>
                <span className="w-6 text-right text-gray-600 dark:text-gray-400">{count}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Recent reviews */}
      <div className="space-y-4">
        {summary.recent.map((review) => (
          <div
            key={review.id}
            className="rounded-xl border border-gray-200 p-4 dark:border-gray-700"
          >
            <div className="mb-1 flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-orange-600 text-xs font-bold text-white">
                {(review.user.firstName || review.user.username || "?").charAt(0).toUpperCase()}
              </div>
              <div>
                <div className="text-sm font-bold text-foreground">
                  {review.user.firstName || review.user.username}
                  {review.verifiedStay && (
                    <span className="ml-2 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-600 dark:text-emerald-400">
                      Verified stay
                    </span>
                  )}
                </div>
                <div className="flex gap-0.5 text-amber-500">
                  {[1, 2, 3, 4, 5].map((n) => (
                    <Star
                      key={n}
                      className={cn("size-3", n <= review.rating && "fill-amber-500")}
                    />
                  ))}
                </div>
              </div>
            </div>
            <p className="text-sm text-gray-700 dark:text-gray-300">{review.comment}</p>
            {review.photos.length > 0 && (
              <div className="mt-2 flex gap-2">
                {review.photos.map((photo, i) => (
                  <img
                    key={i}
                    src={photo}
                    alt="Review photo"
                    className="h-16 w-20 rounded-lg object-cover"
                  />
                ))}
              </div>
            )}
            {review.reply && (
              <div className="mt-3 rounded-lg bg-gray-50 p-3 text-sm dark:bg-gray-800">
                <div className="mb-0.5 flex items-center gap-1.5 text-xs font-bold text-gray-600 dark:text-gray-400">
                  <MessageSquareReply className="size-3.5" /> Landlord response
                </div>
                {review.reply}
              </div>
            )}
            {isOwner && (
              <div className="mt-3 flex gap-2">
                <input
                  value={replyText[review.id] ?? ""}
                  onChange={(e) => setReplyText((r) => ({ ...r, [review.id]: e.target.value }))}
                  placeholder={review.reply ? "Update your reply…" : "Reply to this review…"}
                  className="min-w-0 flex-1 rounded-lg border border-gray-300 bg-card px-3 py-2 text-sm outline-none focus:border-orange-500 dark:border-gray-600"
                />
                <Button
                  size="sm"
                  className="bg-orange-600 text-white hover:bg-orange-700"
                  disabled={!replyText[review.id]?.trim() || replyMutation.isPending}
                  onClick={() =>
                    replyMutation.mutate({
                      reviewId: review.id,
                      reply: replyText[review.id].trim(),
                    })
                  }
                >
                  Reply
                </Button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
