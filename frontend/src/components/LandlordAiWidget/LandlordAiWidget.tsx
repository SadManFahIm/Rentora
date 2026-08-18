import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { BarChart3, Bot, Loader2, TrendingDown, TrendingUp } from "lucide-react";
import roomService from "../../services/roomService";
import tier4Service, {
  type DemandForecast,
  type LandlordInsight,
} from "../../services/tier4Service";
import { cn } from "../../lib/utils";
import { Button } from "../ui/button";

/**
 * Landlord AI widget (Tier 4) — two grounded tools for landlords:
 *
 * 1. **Landlord Copilot** — pick one of your listings and get a diagnosis
 *    (price vs area market, 30-day interest, listing-quality suggestions)
 *    built from real booking/wishlist data and public market stats.
 * 2. **Demand Forecast** — per-area demand index + 30-day trend from
 *    anonymized booking/wishlist/view counts.
 */
export default function LandlordAiWidget() {
  const { data: insights } = useQuery({
    queryKey: ["room-insights"],
    queryFn: roomService.getInsights,
  });
  const rooms = insights?.rooms ?? [];

  const [listingId, setListingId] = useState<number | null>(null);
  const [insight, setInsight] = useState<LandlordInsight | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [area, setArea] = useState("Uttara");
  const { data: forecast } = useQuery({
    queryKey: ["demand-forecast", area],
    queryFn: () => tier4Service.forecast(area),
    staleTime: 5 * 60_000,
  });

  const analyze = async () => {
    if (!listingId) return;
    setLoading(true);
    setError("");
    try {
      setInsight(await tier4Service.landlordInsight(listingId));
    } catch {
      setError("Couldn't analyze this listing right now.");
    } finally {
      setLoading(false);
    }
  };

  const positionLabel =
    insight?.price_compare.position === "above_market"
      ? "Above area median"
      : insight?.price_compare.position === "below_market"
        ? "Below area median"
        : "At area median";

  return (
    <div className="grid gap-4 md:grid-cols-2">
      {/* Landlord Copilot */}
      <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900">
        <div className="mb-3 flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
            <Bot className="size-4" />
          </div>
          <div>
            <h3 className="font-display text-sm font-bold text-foreground">Landlord Copilot</h3>
            <p className="text-[11px] text-gray-500 dark:text-gray-400">
              Why isn&apos;t my listing getting bookings?
            </p>
          </div>
        </div>

        <div className="space-y-2 text-sm">
          <select
            value={listingId ?? ""}
            onChange={(e) => setListingId(e.target.value ? Number(e.target.value) : null)}
            className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-emerald-500/40 dark:border-gray-600 dark:bg-gray-900"
            aria-label="Choose a listing to analyze"
          >
            <option value="">Select a listing…</option>
            {rooms.map((r) => (
              <option key={r.id} value={r.id}>
                {r.title}
              </option>
            ))}
          </select>
          <Button
            type="button"
            size="sm"
            onClick={analyze}
            disabled={!listingId || loading}
            className="w-full"
          >
            {loading ? <Loader2 className="size-3.5 animate-spin" /> : "Analyze listing"}
          </Button>

          {error && <p className="text-xs text-rose-600">{error}</p>}

          {insight && (
            <div className="space-y-2 rounded-lg border border-gray-100 p-3 text-xs dark:border-gray-800">
              <div className="flex flex-wrap gap-1.5">
                <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 font-semibold text-emerald-700 dark:text-emerald-400">
                  ৳{insight.price_compare.listing_price.toLocaleString()}/mo
                </span>
                {insight.price_compare.market_median != null && (
                  <span className="rounded-full bg-gray-200/60 px-2 py-0.5 text-gray-600 dark:bg-gray-700 dark:text-gray-300">
                    Area median ৳{insight.price_compare.market_median.toLocaleString()}
                  </span>
                )}
                <span
                  className={cn(
                    "rounded-full px-2 py-0.5 font-semibold",
                    insight.price_compare.position === "above_market"
                      ? "bg-rose-500/10 text-rose-600"
                      : "bg-emerald-500/10 text-emerald-600"
                  )}
                >
                  {positionLabel}
                </span>
              </div>
              <p className="text-gray-600 dark:text-gray-400">
                <b>30-day interest:</b> {insight.interest_30d.bookings} bookings ·{" "}
                {insight.interest_30d.wishlist_saves} saves
              </p>
              {insight.suggestions.length > 0 && (
                <ul className="list-inside list-disc space-y-0.5 text-gray-600 dark:text-gray-400">
                  {insight.suggestions.map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Demand forecast */}
      <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900">
        <div className="mb-3 flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-500/10 text-indigo-600 dark:text-indigo-400">
            <BarChart3 className="size-4" />
          </div>
          <div>
            <h3 className="font-display text-sm font-bold text-foreground">Demand Forecast</h3>
            <p className="text-[11px] text-gray-500 dark:text-gray-400">
              30-day area demand from anonymized signals
            </p>
          </div>
        </div>

        <div className="space-y-2 text-sm">
          <select
            value={area}
            onChange={(e) => setArea(e.target.value)}
            className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-indigo-500/40 dark:border-gray-600 dark:bg-gray-900"
            aria-label="Choose an area for the demand forecast"
          >
            {[
              "Uttara",
              "Dhanmondi",
              "Mirpur",
              "Gulshan",
              "Banani",
              "Mohammadpur",
              "Bashundhara",
            ].map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>

          {forecast && <ForecastBody forecast={forecast} />}
        </div>
      </div>
    </div>
  );
}

function ForecastBody({ forecast }: { forecast: DemandForecast }) {
  if (forecast.demand_index == null) {
    return (
      <div className="rounded-lg bg-gray-50 p-3 text-xs text-gray-600 dark:bg-gray-800/60 dark:text-gray-400">
        <p className="mb-1 font-semibold text-foreground">Insufficient data</p>
        {forecast.note}
      </div>
    );
  }
  const max = Math.max(...forecast.weekly_series, 1);
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <span className="text-2xl font-bold text-foreground">{forecast.demand_index}</span>
        <span className="text-xs text-gray-500 dark:text-gray-400">/ 100 demand index</span>
        {forecast.direction === "rising" && (
          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-xs font-semibold text-emerald-600">
            <TrendingUp className="size-3" /> Rising
          </span>
        )}
        {forecast.direction === "falling" && (
          <span className="inline-flex items-center gap-1 rounded-full bg-rose-500/10 px-2 py-0.5 text-xs font-semibold text-rose-600">
            <TrendingDown className="size-3" /> Falling
          </span>
        )}
      </div>

      {/* Weekly activity mini-bars */}
      <div className="flex h-16 items-end gap-1">
        {forecast.weekly_series.map((v, i) => (
          <div
            key={i}
            title={`Week ${i + 1}: ${v} signals`}
            className="flex-1 rounded-t bg-indigo-500/60"
            style={{ height: `${Math.max(6, (v / max) * 100)}%` }}
          />
        ))}
      </div>

      <p className="text-[11px] text-gray-500 dark:text-gray-400">
        {forecast.forecast_30d != null &&
          `~${forecast.forecast_30d} signals expected in the next 30 days. `}
        {forecast.note}
      </p>
    </div>
  );
}
