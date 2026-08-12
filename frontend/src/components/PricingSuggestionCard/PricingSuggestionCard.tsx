import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Clock, Loader2, Sparkles, TrendingUp } from "lucide-react";
import { toast } from "sonner";
import { getPricingSuggestion } from "../../services/pricingService";
import roomService from "../../services/roomService";
import { getApiErrorMessage } from "../../services/errors";
import { cn } from "../../lib/utils";
import { Button } from "../ui/button";

const demandTone: Record<string, string> = {
  Low: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
  Moderate: "bg-amber-500/10 text-amber-600 dark:text-amber-400",
  High: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
  "Very High": "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
};

/**
 * AI pricing suggestion (v2) — recommended range, demand, time-to-rent,
 * confidence and *why*. The landlord explicitly applies the suggested price
 * via the normal room update; nothing changes automatically.
 */
export default function PricingSuggestionCard({ roomId }: { roomId: number }) {
  const [open, setOpen] = useState(false);
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ["pricing-suggestion", roomId],
    queryFn: () => getPricingSuggestion(roomId),
    enabled: open,
    staleTime: 5 * 60 * 1000,
  });

  const apply = useMutation({
    mutationFn: (price: number) => roomService.updateRoom(roomId, { price }),
    onSuccess: () => {
      toast.success("Suggested price applied to your listing.");
      void queryClient.invalidateQueries({ queryKey: ["room-insights"] });
      setOpen(false);
    },
    onError: (err) => toast.error(getApiErrorMessage(err, "Could not apply the suggested price.")),
  });

  return (
    <div className="rounded-xl border border-violet-200 bg-gradient-to-br from-violet-50/80 to-amber-50/60 p-3.5 dark:border-violet-900/50 dark:from-violet-950/30 dark:to-amber-950/20">
      <button
        type="button"
        className="flex w-full items-center justify-between gap-2 text-left"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="flex items-center gap-2 text-sm font-bold text-foreground">
          <Sparkles className="size-4 text-violet-600 dark:text-violet-400" />
          AI Pricing Suggestion
          {data?.recommended_price != null && (
            <span className="rounded-full bg-violet-600/10 px-2 py-0.5 text-xs font-semibold text-violet-700 dark:text-violet-300">
              ৳{data.recommended_price.toLocaleString()}
            </span>
          )}
        </span>
        <span className="text-xs text-gray-500 dark:text-gray-400">{open ? "Hide" : "Show"} ▾</span>
      </button>

      {open && (
        <div className="mt-3 flex flex-col gap-3">
          {isLoading && (
            <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
              <Loader2 className="size-3.5 animate-spin" /> Computing from market data…
            </div>
          )}
          {error && (
            <p className="text-xs text-rose-600 dark:text-rose-400">
              Couldn't load the suggestion: {getApiErrorMessage(error, "try again later.")}
            </p>
          )}

          {data && (
            <>
              <div className="grid grid-cols-3 gap-2 text-center">
                <div className="rounded-lg bg-white/70 p-2 dark:bg-gray-900/50">
                  <div className="text-[10px] text-gray-500 dark:text-gray-400">Range</div>
                  <div className="text-xs font-bold text-foreground">
                    {data.min_price != null ? `৳${data.min_price.toLocaleString()}` : "—"} –{" "}
                    {data.max_price != null ? `৳${data.max_price.toLocaleString()}` : "—"}
                  </div>
                </div>
                <div className="rounded-lg bg-white/70 p-2 dark:bg-gray-900/50">
                  <div className="flex items-center justify-center gap-1 text-[10px] text-gray-500 dark:text-gray-400">
                    <TrendingUp className="size-3" /> Demand
                  </div>
                  <span
                    className={cn(
                      "inline-flex rounded-full px-2 py-0.5 text-xs font-bold",
                      demandTone[data.demand_label] ?? demandTone.Low
                    )}
                  >
                    {data.demand_label}
                  </span>
                </div>
                <div className="rounded-lg bg-white/70 p-2 dark:bg-gray-900/50">
                  <div className="text-[10px] text-gray-500 dark:text-gray-400">Confidence</div>
                  <div className="text-xs font-bold text-foreground">
                    {Math.round(data.confidence * 100)}%
                  </div>
                </div>
              </div>

              {data.time_to_rent.available ? (
                <div className="flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-400">
                  <Clock className="size-3.5" />
                  Estimated time-to-rent: {data.time_to_rent.days_min}–{data.time_to_rent.days_max}{" "}
                  days
                </div>
              ) : (
                <div className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400">
                  <Clock className="size-3.5" /> Time-to-rent:{" "}
                  {data.time_to_rent.detail ?? "insufficient data"}
                </div>
              )}

              {data.reasons.length > 0 && (
                <ul className="list-inside list-disc space-y-0.5 text-xs text-gray-600 dark:text-gray-400">
                  {data.reasons.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
              )}

              <div className="flex gap-2">
                <Button
                  size="sm"
                  className="flex-1 bg-violet-600 text-white hover:bg-violet-700"
                  disabled={apply.isPending || data.recommended_price == null}
                  onClick={() =>
                    data.recommended_price != null && apply.mutate(data.recommended_price)
                  }
                >
                  {apply.isPending ? (
                    <Loader2 className="size-3.5 animate-spin" />
                  ) : (
                    <Check className="size-3.5" />
                  )}
                  Use ৳{data.recommended_price?.toLocaleString() ?? "—"}
                </Button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
