import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { BarChart3, Loader2, Mail, TrendingDown, TrendingUp } from "lucide-react";
import { toast } from "sonner";
import marketReportService, { type MarketReport } from "../../services/marketReportService";
import { cn } from "../../lib/utils";
import { Button } from "../ui/button";

const reportKeys = { all: ["market-report"] as const };

/**
 * Phase 15 — C6 rental market report card (admin analytics).
 *
 * Public, read-only digest: per-area avg/median rents, demand direction,
 * 30-day forecast and week-over-week price movement. The admin "Generate &
 * email" action writes this week's price snapshot and emails opted-in
 * landlords — the weekly Monday beat does the same automatically.
 */
export default function MarketReportCard() {
  const [generating, setGenerating] = useState(false);
  const [generated, setGenerated] = useState<{ week_label: string; areas: number } | null>(null);

  const {
    data: report,
    isLoading,
    isError,
    refetch,
  } = useQuery<MarketReport>({
    queryKey: reportKeys.all,
    queryFn: () => marketReportService.get(),
    staleTime: 5 * 60 * 1000,
  });

  const generate = async () => {
    setGenerating(true);
    try {
      const result = await marketReportService.generate();
      setGenerated(result);
      toast.success(`Market report generated — ${result.areas} areas recorded.`);
      void refetch();
    } catch {
      toast.error("Could not generate the market report right now.");
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div className="rounded-2xl border border-gray-200 bg-card p-4 dark:border-gray-800">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-orange-500/10 text-orange-600 dark:text-orange-400">
            <BarChart3 className="size-4" />
          </div>
          <div>
            <h4 className="font-display text-sm font-bold text-foreground">Rental market report</h4>
            <p className="text-[11px] text-gray-500 dark:text-gray-400">
              {report ? report.week_label : "Weekly digest — live listing, booking & search data"}
            </p>
          </div>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="text-xs"
          onClick={generate}
          disabled={generating}
        >
          {generating ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <Mail className="size-3.5" />
          )}
          Generate &amp; email landlords
        </Button>
      </div>

      {generated && (
        <div className="mb-3 rounded-lg bg-emerald-500/10 px-3 py-2 text-xs font-semibold text-emerald-600 dark:text-emerald-400">
          Snapshot written for {generated.week_label} — {generated.areas} areas. Opted-in landlords
          were emailed; the Monday beat keeps this weekly.
        </div>
      )}

      {isLoading && (
        <div className="flex items-center gap-2 py-4 text-xs text-gray-500">
          <Loader2 className="size-3.5 animate-spin" /> Building the market digest…
        </div>
      )}
      {isError && !report && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-600 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-400">
          Could not load the market report.{" "}
          <button type="button" className="underline" onClick={() => refetch()}>
            Try again
          </button>
        </div>
      )}

      {report && (
        <div className="space-y-3">
          {/* Highlights */}
          {report.highlights.length > 0 && (
            <ul className="space-y-1">
              {report.highlights.map((h) => (
                <li
                  key={`${h.kind}-${h.area}`}
                  className="flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-400"
                >
                  {h.kind === "rising" ? (
                    <TrendingUp className="size-3.5 shrink-0 text-emerald-500" />
                  ) : (
                    <TrendingDown className="size-3.5 shrink-0 text-orange-500" />
                  )}
                  {h.text}
                </li>
              ))}
            </ul>
          )}

          {report.baseline && (
            <p className="text-[11px] text-gray-500 dark:text-gray-400">
              First snapshot — no week-over-week movement yet (baseline week).
            </p>
          )}

          {/* Area table */}
          {report.areas.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-gray-100 text-[10px] uppercase tracking-wide text-gray-500 dark:border-gray-800 dark:text-gray-400">
                    <th className="py-1.5 pr-2 font-semibold">Area</th>
                    <th className="py-1.5 pr-2 font-semibold">Avg ৳</th>
                    <th className="py-1.5 pr-2 font-semibold">Median ৳</th>
                    <th className="py-1.5 pr-2 font-semibold">Demand</th>
                    <th className="py-1.5 pr-2 font-semibold">Forecast 30d</th>
                    <th className="py-1.5 font-semibold">WoW</th>
                  </tr>
                </thead>
                <tbody>
                  {report.areas.slice(0, 12).map((row) => (
                    <tr
                      key={row.area}
                      className="border-b border-gray-50 text-gray-600 dark:border-gray-800/60 dark:text-gray-300"
                    >
                      <td className="py-1.5 pr-2 font-semibold text-foreground">{row.area}</td>
                      <td className="py-1.5 pr-2">
                        {row.avg_price != null ? row.avg_price.toLocaleString() : "—"}
                      </td>
                      <td className="py-1.5 pr-2">
                        {row.median_price != null ? row.median_price.toLocaleString() : "—"}
                      </td>
                      <td className="py-1.5 pr-2">
                        {row.demand_index != null ? (
                          <span
                            className={cn(
                              "rounded-full px-1.5 py-0.5 text-[10px] font-semibold",
                              row.direction === "rising"
                                ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                                : row.direction === "falling"
                                  ? "bg-orange-500/10 text-orange-600 dark:text-orange-400"
                                  : "bg-gray-500/10 text-gray-500"
                            )}
                          >
                            {row.direction ?? "stable"} · {row.demand_index}
                          </span>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="py-1.5 pr-2">
                        {row.forecast_30d != null ? `+${row.forecast_30d}` : "—"}
                      </td>
                      <td className="py-1.5">
                        {row.price_change_pct != null ? (
                          <span
                            className={cn(
                              "font-semibold",
                              row.price_change_pct > 0
                                ? "text-emerald-600 dark:text-emerald-400"
                                : row.price_change_pct < 0
                                  ? "text-orange-600 dark:text-orange-400"
                                  : "text-gray-500"
                            )}
                          >
                            {row.price_change_pct > 0 ? "+" : ""}
                            {row.price_change_pct}%
                          </span>
                        ) : (
                          "—"
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-xs text-gray-500 dark:text-gray-400">
              No listing data yet — the digest appears once rooms are live.
            </p>
          )}

          <p className="text-[10px] leading-relaxed text-gray-400 dark:text-gray-500">
            {report.note}
          </p>
        </div>
      )}
    </div>
  );
}
