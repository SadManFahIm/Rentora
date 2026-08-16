import {
  Activity,
  ArrowDownRight,
  BarChart3,
  Loader2,
  MousePointerClick,
  Users,
} from "lucide-react";

import { useAnalyticsSummary } from "../../hooks/useAnalytics";

function StepRow({
  step,
  count,
  previous,
  isFirst,
}: {
  step: string;
  count: number;
  previous: number | null;
  isFirst: boolean;
}) {
  const drop = previous !== null && previous > 0 ? ((previous - count) / previous) * 100 : null;
  const label = step.replace(/_/g, " ");
  return (
    <div className="flex items-center gap-3 rounded-lg border border-gray-100 bg-gray-50 px-3 py-2 dark:border-gray-800 dark:bg-gray-800/50">
      <div className="min-w-0 flex-1">
        <div className="truncate text-xs font-semibold capitalize text-gray-700 dark:text-gray-300">
          {label}
        </div>
        {drop !== null && !isFirst && (
          <div className="flex items-center gap-1 text-[0.65rem] text-gray-500 dark:text-gray-400">
            <ArrowDownRight className="size-3" />
            {drop.toFixed(0)}% drop-off
          </div>
        )}
      </div>
      <div className="font-display text-sm font-bold text-foreground">{count}</div>
    </div>
  );
}

export default function AdminAnalyticsPanel() {
  const { data, isLoading, isError, refetch } = useAnalyticsSummary(30);

  if (isLoading) {
    return (
      <div className="flex min-h-[240px] items-center justify-center text-gray-500">
        <Loader2 className="mr-2 size-4 animate-spin" /> Loading analytics…
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="rounded-2xl border border-red-200 bg-red-50 p-6 text-sm text-red-600 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-400">
        Could not load analytics.{" "}
        <button type="button" className="underline" onClick={() => refetch()}>
          Try again
        </button>
      </div>
    );
  }

  const steps = data.funnelSteps;
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
        <BarChart3 className="size-4" /> Last {data.days} days · first-party, self-hosted
      </div>

      {/* Totals */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {[
          { icon: Activity, label: "Events", value: data.totals.events },
          { icon: MousePointerClick, label: "Sessions", value: data.totals.sessions },
          { icon: Users, label: "Active users", value: data.totals.activeUsers },
        ].map(({ icon: Icon, label, value }) => (
          <div
            key={label}
            className="rounded-2xl border border-gray-200 bg-card p-4 dark:border-gray-800"
          >
            <div className="flex items-center gap-2 text-gray-600 dark:text-gray-400">
              <Icon className="size-4" />
              <span className="text-xs font-medium">{label}</span>
            </div>
            <div className="mt-1 font-display text-2xl font-bold text-foreground">{value}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Conversion funnel */}
        <div className="rounded-2xl border border-gray-200 bg-card p-4 dark:border-gray-800">
          <h4 className="mb-2 font-display text-sm font-bold text-foreground">
            Conversion funnel (distinct users)
          </h4>
          <div className="space-y-2">
            {steps.map((step, index) => (
              <StepRow
                key={step}
                step={step}
                count={data.funnel[step] ?? 0}
                previous={index > 0 ? (data.funnel[steps[index - 1]] ?? 0) : null}
                isFirst={index === 0}
              />
            ))}
          </div>
          <p className="mt-2 text-[0.65rem] text-gray-500 dark:text-gray-400">{data.note}</p>
        </div>

        {/* Top events + pages */}
        <div className="space-y-4">
          <div className="rounded-2xl border border-gray-200 bg-card p-4 dark:border-gray-800">
            <h4 className="mb-2 font-display text-sm font-bold text-foreground">Top events</h4>
            <ul className="space-y-1.5">
              {data.topEvents.length === 0 && (
                <li className="text-xs text-gray-500">No events captured yet.</li>
              )}
              {data.topEvents.map((e) => (
                <li
                  key={e.event}
                  className="flex items-center justify-between text-xs text-gray-600 dark:text-gray-400"
                >
                  <span className="capitalize">{e.event.replace(/_/g, " ")}</span>
                  <span className="font-semibold text-foreground">{e.count}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className="rounded-2xl border border-gray-200 bg-card p-4 dark:border-gray-800">
            <h4 className="mb-2 font-display text-sm font-bold text-foreground">Top pages</h4>
            <ul className="space-y-1.5">
              {data.topPages.length === 0 && (
                <li className="text-xs text-gray-500">No page views captured yet.</li>
              )}
              {data.topPages.map((p) => (
                <li
                  key={p.path}
                  className="flex items-center justify-between text-xs text-gray-600 dark:text-gray-400"
                >
                  <span className="truncate font-mono">{p.path}</span>
                  <span className="ml-2 shrink-0 font-semibold text-foreground">{p.count}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
