import { useState } from "react";
import { ArrowDown, ArrowUp, Loader2, Minus, TrendingUp } from "lucide-react";
import tier5Service, { type PriceRecommendation } from "../../services/tier5Service";
import { cn } from "../../lib/utils";
import { Button } from "../ui/button";

/**
 * Tier-5 price recommendation — per-listing demand+market suggestion.
 *
 * Shows the raise/hold/lower verdict, the suggested price, and the reasons
 * behind it. Never auto-changes the price; it's a review aid for the owner.
 */
export default function PriceRecommendationCard({ roomId }: { roomId: number }) {
  const [rec, setRec] = useState<PriceRecommendation | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const fetchRec = async () => {
    setLoading(true);
    setError("");
    try {
      setRec(await tier5Service.priceRecommendation(roomId));
    } catch {
      setError("Couldn't get a recommendation right now.");
    } finally {
      setLoading(false);
    }
  };

  const DirectionIcon =
    rec?.direction === "raise" ? ArrowUp : rec?.direction === "lower" ? ArrowDown : Minus;

  const directionColor =
    rec?.direction === "raise"
      ? "text-emerald-600 dark:text-emerald-400"
      : rec?.direction === "lower"
        ? "text-orange-600 dark:text-orange-400"
        : "text-gray-500 dark:text-gray-400";

  return (
    <div className="rounded-xl border border-gray-200 bg-card p-4 dark:border-gray-800">
      <div className="mb-2 flex items-center gap-2">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
          <TrendingUp className="size-4" />
        </div>
        <h3 className="font-display text-sm font-bold text-foreground">Price recommendation</h3>
      </div>

      {!rec && !loading && !error && (
        <Button variant="outline" size="sm" className="text-xs" onClick={fetchRec}>
          Get recommendation
        </Button>
      )}

      {loading && (
        <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
          <Loader2 className="size-3.5 animate-spin" /> Analyzing demand &amp; market…
        </div>
      )}

      {error && <p className="text-xs font-medium text-red-600 dark:text-red-400">{error}</p>}

      {rec && !loading && (
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <DirectionIcon className={cn("size-5", directionColor)} />
            <div>
              <div className="flex items-baseline gap-2">
                <span className="font-display text-lg font-bold text-foreground">
                  ৳{rec.suggested_price.toLocaleString()}
                </span>
                <span className="text-xs text-gray-500 dark:text-gray-400">
                  vs ৳{rec.current_price.toLocaleString()} now
                </span>
              </div>
              <span
                className={cn(
                  "inline-block rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide",
                  rec.confidence === "high"
                    ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                    : rec.confidence === "medium"
                      ? "bg-amber-500/10 text-amber-600 dark:text-amber-400"
                      : "bg-gray-500/10 text-gray-500 dark:text-gray-400"
                )}
              >
                {rec.direction} · {rec.confidence} confidence
              </span>
            </div>
          </div>
          <ul className="space-y-1">
            {rec.reasons.map((reason) => (
              <li key={reason} className="flex gap-2 text-xs text-gray-600 dark:text-gray-400">
                <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-emerald-500" />
                {reason}
              </li>
            ))}
          </ul>
          <p className="text-[11px] text-gray-400 dark:text-gray-500">{rec.note}</p>
        </div>
      )}
    </div>
  );
}
