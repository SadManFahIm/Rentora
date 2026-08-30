import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Loader2, ShieldAlert, BellRing } from "lucide-react";
import {
  useAiAlerts,
  useAiAlertRules,
  useAlertLifecycle,
  useAiCost,
  useAiDrift,
  useAiErrors,
  useAiFeatures,
  useAiFeatureDetail,
  useAiModelCompare,
  useAiModels,
  useAiPerformance,
  useAiPrompts,
  useAiProviders,
  useAiQuality,
  useAiSummary,
  useCreateAiAlertRule,
  useDeleteAiAlertRule,
  useEvaluateAiAlerts,
  useUpdateAiAlertRule,
} from "../../hooks/useAiIntelligence";
import type {
  AiAlert,
  AiAlertRule,
  AiFeatureRow,
  AiModelSnapshot,
  AiTrendPoint,
  NewAiAlertRule,
} from "../../services/aiIntelligenceService";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";
import { cn } from "../../lib/utils";

// ============================================================
// ADMIN AI PANEL — Phase 18 AI Intelligence Dashboard + Alerts
// ============================================================

type AiView =
  | "overview"
  | "features"
  | "models"
  | "providers"
  | "cost"
  | "performance"
  | "errors"
  | "quality"
  | "drift"
  | "prompts"
  | "alerts";

const AI_VIEWS: AiView[] = [
  "overview",
  "features",
  "models",
  "providers",
  "cost",
  "performance",
  "errors",
  "quality",
  "drift",
  "prompts",
  "alerts",
];

const driftTone: Record<string, string> = {
  healthy: "bg-emerald-500/10 text-emerald-500",
  warning: "bg-amber-500/10 text-amber-500",
  critical: "bg-red-500/10 text-red-500",
  unknown: "bg-gray-500/10 text-gray-500",
};

const severityTone: Record<string, string> = {
  info: "bg-blue-500/10 text-blue-500",
  warning: "bg-amber-500/10 text-amber-500",
  critical: "bg-red-500/10 text-red-500",
};

const alertStatusTone: Record<string, string> = {
  triggered: "bg-red-500/10 text-red-500",
  acknowledged: "bg-amber-500/10 text-amber-500",
  resolved: "bg-emerald-500/10 text-emerald-500",
  suppressed: "bg-gray-500/10 text-gray-500",
};

const NO_DATA = "—";

function fmtUsd(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return NO_DATA;
  const v = Math.abs(n);
  const digits = v >= 1 ? 2 : v >= 0.001 ? 4 : 8;
  return `$${n.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}`;
}

function fmtMs(n: number | null | undefined): string {
  return n == null ? NO_DATA : `${Math.round(n).toLocaleString()} ms`;
}

function fmtPct(n: number | null | undefined): string {
  return n == null ? NO_DATA : `${n.toFixed(2)}%`;
}

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return NO_DATA;
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
}

function Badge({ children, tone }: { children: React.ReactNode; tone: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold",
        tone
      )}
    >
      {children}
    </span>
  );
}

function Card({
  title,
  subtitle,
  children,
  className,
}: {
  title?: string;
  subtitle?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-gray-200 bg-card p-5 dark:border-gray-800",
        className
      )}
    >
      {title && (
        <div className="mb-3">
          <h3 className="font-display text-sm font-bold text-foreground">{title}</h3>
          {subtitle && (
            <p className="mt-0.5 text-xs text-gray-600 dark:text-gray-400">{subtitle}</p>
          )}
        </div>
      )}
      {children}
    </div>
  );
}

function Stat({
  label,
  value,
  sub,
  tone = "text-foreground",
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: string;
}) {
  return (
    <div className="rounded-2xl border border-gray-200 bg-card p-4 dark:border-gray-800">
      <div className="text-xs text-gray-600 dark:text-gray-400">{label}</div>
      <div className={cn("mt-1 truncate font-display text-xl font-bold", tone)}>{value}</div>
      {sub && <div className="mt-0.5 truncate text-xs text-gray-500 dark:text-gray-400">{sub}</div>}
    </div>
  );
}

function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-15 text-gray-600 dark:text-gray-400">
      <Loader2 className="size-4 animate-spin" /> {label}
    </div>
  );
}

function Empty({ message }: { message: string }) {
  return (
    <div className="py-15 text-center text-sm text-gray-600 dark:text-gray-400">{message}</div>
  );
}

function BarRow({
  label,
  value,
  max,
  detail,
}: {
  label: string;
  value: number;
  max: number;
  detail?: string;
}) {
  const pct = max > 0 ? Math.max(2, (value / max) * 100) : 0;
  return (
    <div className="flex items-center gap-3">
      <div className="w-44 shrink-0 truncate text-xs text-gray-700 dark:text-gray-300">{label}</div>
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
        <div className="h-full rounded-full bg-orange-500" style={{ width: `${pct}%` }} />
      </div>
      <div className="w-24 shrink-0 text-right text-xs text-gray-600 dark:text-gray-400">
        {detail ?? value}
      </div>
    </div>
  );
}

/** Generic SVG trend chart: bars for the primary series + optional line. */
function TrendChart({
  points,
  secondary,
  formatValue,
  ariaLabel,
}: {
  points: { date: string; value: number }[];
  secondary?: { date: string; value: number }[];
  formatValue: (v: number) => string;
  ariaLabel: string;
}) {
  const W = 720;
  const H = 200;
  const PAD = { top: 16, right: 16, bottom: 28, left: 44 };
  const iw = W - PAD.left - PAD.right;
  const ih = H - PAD.top - PAD.bottom;

  const maxPrimary = Math.max(1, ...points.map((p) => p.value));
  const maxSecondary = Math.max(1, ...[...(secondary ?? [])].map((p) => p.value));
  const n = points.length;
  const bw = n > 0 ? iw / n : 1;
  const toY = (v: number, maxV: number) => PAD.top + ih - (v / maxV) * ih;

  const linePoints =
    (secondary ?? [])
      .map((p, i) => `${PAD.left + i * bw + bw / 2},${toY(p.value, maxSecondary)}`)
      .join(" ") || "";

  const ticks = points.filter((_, i) => i % 5 === 0 || i === n - 1);

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={ariaLabel}>
        {[0.25, 0.5, 0.75, 1].map((f) => (
          <line
            key={f}
            x1={PAD.left}
            y1={PAD.top + ih - f * ih}
            x2={W - PAD.right}
            y2={PAD.top + ih - f * ih}
            stroke="currentColor"
            strokeOpacity="0.08"
            strokeDasharray="3 4"
          />
        ))}
        {points.map((p, i) => (
          <rect
            key={`${p.date}-${i}`}
            x={PAD.left + i * bw + bw * 0.2}
            y={toY(p.value, maxPrimary)}
            width={Math.max(2, bw * 0.6)}
            height={Math.max(0, ih - (toY(p.value, maxPrimary) - PAD.top))}
            rx={2}
            fill="#f97316"
            fillOpacity={p.value > 0 ? 0.85 : 0.12}
          />
        ))}
        {linePoints && (
          <polyline
            points={linePoints}
            fill="none"
            stroke="#0ea5e9"
            strokeWidth="2"
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        )}
        {ticks.map((p) => {
          const i = points.indexOf(p);
          const date = new Date(p.date.endsWith("T00:00:00") ? p.date : `${p.date}T00:00:00`);
          return (
            <text
              key={`${p.date}-tick`}
              x={PAD.left + i * bw + bw / 2}
              y={H - 8}
              textAnchor="middle"
              className="fill-current text-[10px] text-gray-400"
            >
              {Number.isNaN(date.getTime())
                ? p.date
                : date.toLocaleDateString(undefined, { month: "short", day: "numeric" })}
            </text>
          );
        })}
        <text
          x={W - PAD.right}
          y={PAD.top - 4}
          textAnchor="end"
          className="fill-current text-[10px] text-gray-400"
        >
          {points.length > 0 ? formatValue(maxPrimary) : ""}
        </text>
        {secondary && secondary.length > 0 && (
          <text x={PAD.left} y={PAD.top - 4} className="fill-current text-[10px] text-sky-500">
            {formatValue(maxSecondary)}
          </text>
        )}
      </svg>
    </div>
  );
}

const toChartPoints = (trend: AiTrendPoint[], key: "count" | "costUsd" | "avgLatencyMs") =>
  trend.map((t) => ({ date: t.date, value: t[key] ?? 0 }));

// ---------------------------------------------------------------------------
// Views
// ---------------------------------------------------------------------------

function OverviewView() {
  const { data, isLoading } = useAiSummary(30);
  if (isLoading) return <Loading />;
  if (!data) return <Empty message="No AI telemetry yet." />;
  const trend = data.trend ?? [];
  return (
    <div className="flex flex-col gap-5">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat
          label="Total executions"
          value={data.totalExecutions.toLocaleString()}
          sub="last 30 days"
        />
        <Stat
          label="Success rate"
          value={fmtPct(data.successRate)}
          tone={data.successRate >= 90 ? "text-emerald-500" : "text-amber-500"}
        />
        <Stat
          label="Error rate"
          value={fmtPct(data.errorRate)}
          tone={data.errorRate > 5 ? "text-red-500" : "text-foreground"}
          sub={`${data.failedExecutions.toLocaleString()} failed`}
        />
        <Stat
          label="Avg latency"
          value={fmtMs(data.avgLatencyMs)}
          sub={`p95 ${fmtMs(data.p95LatencyMs)}`}
        />
        <Stat
          label="Est. cost (30d)"
          value={fmtUsd(data.estimatedCostUsd)}
          sub="ESTIMATED USD from telemetry"
          tone="text-amber-600"
        />
        <Stat
          label="Total tokens"
          value={data.totalTokens.toLocaleString()}
          sub={`${data.inputTokens.toLocaleString()} in / ${data.outputTokens.toLocaleString()} out`}
        />
        <Stat
          label="Active features"
          value={data.activeFeatures.toLocaleString()}
          sub={`${data.activeModels.toLocaleString()} model variants`}
        />
        <Stat
          label="Drift status"
          value={data.driftStatus}
          tone={
            data.driftStatus === "critical"
              ? "text-red-500"
              : data.driftStatus === "warning"
                ? "text-amber-500"
                : "text-emerald-500"
          }
        />
      </div>
      <Card title="Execution volume" subtitle="Daily successful/errored executions (last 30 days)">
        <div className="mb-1 flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400">
          <span className="inline-flex items-center gap-1.5">
            <span className="inline-block size-2.5 rounded-sm bg-orange-500" /> Executions
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="inline-block size-2.5 rounded-full border-2 border-red-400" /> —
          </span>
        </div>
        <TrendChart
          points={toChartPoints(trend, "count")}
          secondary={trend
            .filter((t) => t.errors != null)
            .map((t) => ({ date: t.date, value: t.errors ?? 0 }))}
          formatValue={(v) => v.toLocaleString()}
          ariaLabel="Daily AI executions and errors over the last 30 days"
        />
      </Card>
      <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
        <Stat
          label="Fallback rate"
          value={fmtPct(data.fallbackRate)}
          sub="executions routed to a fallback provider"
        />
        <Stat
          label="Open alerts"
          value={data.openAlerts.toLocaleString()}
          sub="triggered + acknowledged"
          tone={data.openAlerts > 0 ? "text-red-500" : "text-emerald-500"}
        />
      </div>
    </div>
  );
}

function FeaturesView() {
  const { data: features, isLoading } = useAiFeatures(30);
  const [selected, setSelected] = useState<AiFeatureRow | null>(null);
  const detail = useAiFeatureDetail(selected?.featureId ?? null, 30);

  if (isLoading) return <Loading />;
  const rows = features ?? [];
  if (rows.length === 0) return <Empty message="No AI features registered yet." />;

  return (
    <div className="flex flex-col gap-5">
      <Card
        title={`Features (${rows.length})`}
        subtitle="Registry features with live telemetry + latest evaluation"
      >
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead>
              <tr className="border-b border-gray-200 text-xs uppercase tracking-wide text-gray-500 dark:border-gray-800">
                <th className="pb-2 pr-3">Feature</th>
                <th className="pb-2 pr-3">Category</th>
                <th className="pb-2 pr-3 text-right">Executions</th>
                <th className="pb-2 pr-3 text-right">Success</th>
                <th className="pb-2 pr-3 text-right">Error</th>
                <th className="pb-2 pr-3 text-right">Avg ms</th>
                <th className="pb-2 pr-3 text-right">Eval score</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((f) => (
                <tr
                  key={f.featureId}
                  onClick={() => setSelected(f)}
                  className={cn(
                    "cursor-pointer border-b border-gray-100 last:border-0 hover:bg-gray-50 dark:border-gray-800/60 dark:hover:bg-gray-800/40",
                    selected?.featureId === f.featureId && "bg-orange-50 dark:bg-orange-950/20"
                  )}
                >
                  <td className="py-2.5 pr-3">
                    <div className="font-semibold text-foreground">
                      {f.name || f.featureId}
                      {!f.isEnabled && (
                        <span className="ml-2 rounded-full bg-gray-500/10 px-2 py-0.5 text-[10px] font-semibold text-gray-500">
                          disabled
                        </span>
                      )}
                    </div>
                    <div className="font-mono text-[11px] text-gray-500">{f.featureId}</div>
                  </td>
                  <td className="py-2.5 pr-3 text-gray-600 dark:text-gray-400">{f.category}</td>
                  <td className="py-2.5 pr-3 text-right">{f.totalExecutions.toLocaleString()}</td>
                  <td className="py-2.5 pr-3 text-right text-emerald-500">
                    {fmtPct(f.successRate)}
                  </td>
                  <td className="py-2.5 pr-3 text-right text-red-500">{fmtPct(f.errorRate)}</td>
                  <td className="py-2.5 pr-3 text-right">{fmtMs(f.avgLatencyMs)}</td>
                  <td className="py-2.5 pr-3 text-right">
                    {f.latestEvaluationScore != null ? f.latestEvaluationScore.toFixed(4) : NO_DATA}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {selected && detail.isLoading && <Loading label="Loading feature detail…" />}
      {selected && detail.data && <FeatureDetailView feature={detail.data} />}
    </div>
  );
}

function FeatureDetailView({
  feature,
}: {
  feature: NonNullable<ReturnType<typeof useAiFeatureDetail>["data"]>;
}) {
  const { usage, performance, reliability, cost, quality, configuration, drift } = feature;
  const maxProvider = Math.max(1, ...cost.byProvider.map((b) => b.costUsd));
  return (
    <Card title={`${feature.name} — drill-down`} subtitle={feature.featureId}>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat
          label="Executions"
          value={usage.totalExecutions.toLocaleString()}
          sub={`${usage.distinctUsers} users`}
        />
        <Stat label="Success rate" value={fmtPct(usage.successRate)} />
        <Stat
          label="Avg latency"
          value={fmtMs(performance.avgLatencyMs)}
          sub={`p95 ${fmtMs(performance.p95LatencyMs)}`}
        />
        <Stat
          label="Cost (30d)"
          value={fmtUsd(cost.estimatedTotalCostUsd)}
          sub="ESTIMATED ✓"
          tone="text-amber-600"
        />
      </div>

      <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Card title="Reliability">
          <div className="space-y-2">
            <BarRow
              label="Error rate"
              value={reliability.errorRate}
              max={100}
              detail={fmtPct(reliability.errorRate)}
            />
            <BarRow
              label="Timeout rate"
              value={reliability.timeoutRate}
              max={100}
              detail={fmtPct(reliability.timeoutRate)}
            />
            <BarRow
              label="Fallback rate"
              value={reliability.fallbackRate}
              max={100}
              detail={fmtPct(reliability.fallbackRate)}
            />
            <BarRow
              label="Provider failures"
              value={reliability.providerFailures}
              max={Math.max(1, reliability.providerFailures)}
            />
          </div>
        </Card>
        <Card title="Quality" subtitle="Latest completed evaluation">
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-600 dark:text-gray-400">Score</span>
              <span className="font-semibold text-foreground">
                {quality.latestEvaluationScore != null
                  ? quality.latestEvaluationScore.toFixed(4)
                  : NO_DATA}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600 dark:text-gray-400">Pass rate</span>
              <span className="font-semibold text-foreground">
                {quality.passRate != null ? `${(quality.passRate * 100).toFixed(1)}%` : NO_DATA}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600 dark:text-gray-400">Regression status</span>
              <span
                className={cn(
                  "font-semibold",
                  quality.regressionStatus === "regression" ? "text-red-500" : "text-emerald-500"
                )}
              >
                {quality.regressionStatus}
              </span>
            </div>
            {quality.regressionCount > 0 && (
              <div className="flex justify-between">
                <span className="text-gray-600 dark:text-gray-400">Regressions</span>
                <span className="font-semibold text-red-500">{quality.regressionCount}</span>
              </div>
            )}
            <div className="flex justify-between">
              <span className="text-gray-600 dark:text-gray-400">Dataset</span>
              <span className="font-mono text-xs text-foreground">
                {quality.datasetKey ?? NO_DATA}
              </span>
            </div>
          </div>
        </Card>
      </div>

      <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Card title="Cost by provider" subtitle="ESTIMATED USD">
          <div className="space-y-2">
            {cost.byProvider.map((b) => (
              <BarRow
                key={b.provider}
                label={b.provider}
                value={b.costUsd}
                max={maxProvider}
                detail={fmtUsd(b.costUsd)}
              />
            ))}
            {cost.byProvider.length === 0 && <Empty message="No spend recorded." />}
          </div>
        </Card>
        <Card title="Configuration">
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-600 dark:text-gray-400">Provider</span>
              <span className="text-foreground">{configuration.activeProvider}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600 dark:text-gray-400">Model</span>
              <span className="text-foreground">{configuration.activeModel}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600 dark:text-gray-400">Active prompt</span>
              <span className="font-mono text-xs text-foreground">
                {configuration.activePrompt || NO_DATA}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600 dark:text-gray-400">Prompt version</span>
              <span className="text-foreground">
                {configuration.activePromptVersion || NO_DATA}
              </span>
            </div>
            {configuration.featureFlagKey && (
              <div className="flex justify-between">
                <span className="text-gray-600 dark:text-gray-400">Flag</span>
                <span className="font-mono text-xs text-foreground">
                  {configuration.featureFlagKey}
                </span>
              </div>
            )}
            <div className="flex justify-between">
              <span className="text-gray-600 dark:text-gray-400">Fallback</span>
              <span className="text-foreground">{configuration.fallbackStrategy || NO_DATA}</span>
            </div>
          </div>
        </Card>
      </div>

      {drift.length > 0 && (
        <Card
          title="Platform drift context"
          className="mt-5"
          subtitle="Derived from Phase 17 drift measurements"
        >
          <DriftTable rows={drift} />
        </Card>
      )}
    </Card>
  );
}

function ModelsView() {
  const { data: models, isLoading } = useAiModels(30);
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [versionA, setVersionA] = useState("");
  const [versionB, setVersionB] = useState("");
  const compare = useAiModelCompare(
    provider && model && versionA && versionB ? { provider, model, versionA, versionB } : null
  );

  return (
    <div className="flex flex-col gap-5">
      <Card title="Model health" subtitle="Telemetry + latest evaluation per (provider, model)">
        {isLoading ? (
          <Loading />
        ) : (models ?? []).length === 0 ? (
          <Empty message="No model telemetry yet." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-sm">
              <thead>
                <tr className="border-b border-gray-200 text-xs uppercase tracking-wide text-gray-500 dark:border-gray-800">
                  <th className="pb-2 pr-3">Provider / Model</th>
                  <th className="pb-2 pr-3 text-right">Executions</th>
                  <th className="pb-2 pr-3 text-right">Success</th>
                  <th className="pb-2 pr-3 text-right">Error</th>
                  <th className="pb-2 pr-3 text-right">Avg ms</th>
                  <th className="pb-2 pr-3 text-right">Cost</th>
                  <th className="pb-2 pr-3 text-right">Eval</th>
                </tr>
              </thead>
              <tbody>
                {(models ?? []).map((m, i) => (
                  <tr
                    key={`${m.provider}:${m.modelName}:${m.modelVersion}:${i}`}
                    className="border-b border-gray-100 last:border-0 dark:border-gray-800/60"
                  >
                    <td className="py-2.5 pr-3">
                      <div className="text-foreground">{m.modelName}</div>
                      <div className="text-[11px] text-gray-500">
                        {m.provider}
                        {m.modelVersion ? ` · v${m.modelVersion}` : ""}
                      </div>
                    </td>
                    <td className="py-2.5 pr-3 text-right">{m.totalExecutions.toLocaleString()}</td>
                    <td className="py-2.5 pr-3 text-right text-emerald-500">
                      {fmtPct(m.successRate)}
                    </td>
                    <td className="py-2.5 pr-3 text-right text-red-500">{fmtPct(m.errorRate)}</td>
                    <td className="py-2.5 pr-3 text-right">{fmtMs(m.avgLatencyMs)}</td>
                    <td className="py-2.5 pr-3 text-right text-amber-600">
                      {fmtUsd(m.estimatedCostUsd)}
                    </td>
                    <td className="py-2.5 pr-3 text-right">
                      {m.latestEvaluationScore != null
                        ? m.latestEvaluationScore.toFixed(4)
                        : NO_DATA}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card
        title="Evaluate two versions"
        subtitle="Read-only A/B of the latest evaluation runs (never switches production)"
      >
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <Input
            placeholder="Provider (e.g. rules)"
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            aria-label="Provider"
          />
          <Input
            placeholder="Model family (e.g. model_x)"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            aria-label="Model family"
          />
          <Input
            placeholder="Variant A (e.g. 1.0)"
            value={versionA}
            onChange={(e) => setVersionA(e.target.value)}
            aria-label="Variant A"
          />
          <Input
            placeholder="Variant B (e.g. 2.0)"
            value={versionB}
            onChange={(e) => setVersionB(e.target.value)}
            aria-label="Variant B"
          />
          <span className="text-xs leading-8 text-gray-500 dark:text-gray-400">
            Matches run model_name or metadata.model_version
          </span>
        </div>
        {compare.isLoading && <Loading label="Comparing…" />}
        {compare.data && (
          <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-3">
            <Snapshot name="Variant A" snap={compare.data.versionA} />
            <Snapshot name="Variant B" snap={compare.data.versionB} />
            <Card title="Deltas (B − A)">
              {compare.data.versionA == null || compare.data.versionB == null ? (
                <Empty message="Need completed evaluation runs for both variants." />
              ) : (
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-600 dark:text-gray-400">Score Δ</span>
                    <span
                      className={cn(
                        "font-semibold",
                        (compare.data.deltas.scoreDelta ?? 0) >= 0
                          ? "text-emerald-500"
                          : "text-red-500"
                      )}
                    >
                      {compare.data.deltas.scoreDelta != null
                        ? compare.data.deltas.scoreDelta.toFixed(4)
                        : NO_DATA}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600 dark:text-gray-400">Latency Δ</span>
                    <span className="text-foreground">
                      {compare.data.deltas.latencyDeltaMs != null
                        ? `${compare.data.deltas.latencyDeltaMs} ms`
                        : NO_DATA}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600 dark:text-gray-400">Cost Δ</span>
                    <span className="text-amber-600">
                      {compare.data.deltas.costDeltaUsd != null
                        ? fmtUsd(compare.data.deltas.costDeltaUsd)
                        : NO_DATA}
                    </span>
                  </div>
                  <div className="flex items-center justify-between pt-1">
                    <span className="text-gray-600 dark:text-gray-400">Winner</span>
                    <Badge
                      tone={
                        compare.data.winner === "a"
                          ? "bg-sky-500/10 text-sky-500"
                          : compare.data.winner === "b"
                            ? "bg-emerald-500/10 text-emerald-500"
                            : "bg-gray-500/10 text-gray-500"
                      }
                    >
                      {compare.data.winner === "b"
                        ? "Variant B"
                        : compare.data.winner === "a"
                          ? "Variant A"
                          : "Tie"}
                    </Badge>
                  </div>
                  <p className="pt-1 text-xs text-gray-500 dark:text-gray-400">
                    Production switch is never automated.
                  </p>
                </div>
              )}
            </Card>
          </div>
        )}
      </Card>
    </div>
  );
}

function Snapshot({ name, snap }: { name: string; snap: AiModelSnapshot | null }) {
  if (!snap)
    return (
      <Card title={name}>
        <Empty message="No run." />
      </Card>
    );
  return (
    <Card title={`${name} — run ${snap.runId}`}>
      <div className="space-y-2 text-sm">
        <div className="flex justify-between">
          <span className="text-gray-600 dark:text-gray-400">Score</span>
          <span className="font-semibold text-foreground">{snap.score}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-600 dark:text-gray-400">Pass rate</span>
          <span className="text-foreground">{`${(snap.passRate * 100).toFixed(1)}%`}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-600 dark:text-gray-400">Avg latency</span>
          <span className="text-foreground">{fmtMs(snap.avgLatencyMs)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-600 dark:text-gray-400">Cost</span>
          <span className="text-amber-600">{fmtUsd(snap.totalCostUsd)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-600 dark:text-gray-400">Dataset</span>
          <span className="font-mono text-xs text-foreground">{snap.datasetKey ?? NO_DATA}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-600 dark:text-gray-400">Completed</span>
          <span className="text-xs text-foreground">{fmtDate(snap.completedAt)}</span>
        </div>
        {Object.keys(snap.metricScores).length > 0 && (
          <div className="pt-1 text-xs text-gray-500 dark:text-gray-400">
            {Object.entries(snap.metricScores)
              .map(([k, v]) => `${k}=${v}`)
              .join(" · ")}
          </div>
        )}
      </div>
    </Card>
  );
}

function ProvidersView() {
  const { data, isLoading } = useAiProviders(30);
  if (isLoading) return <Loading />;
  const rows = data ?? [];
  if (rows.length === 0) return <Empty message="No provider telemetry yet." />;
  return (
    <Card title={`Providers (${rows.length})`} subtitle="Telemetry + latest hourly health window">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] text-left text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-xs uppercase tracking-wide text-gray-500 dark:border-gray-800">
              <th className="pb-2 pr-3">Provider</th>
              <th className="pb-2 pr-3 text-right">Requests</th>
              <th className="pb-2 pr-3 text-right">Success</th>
              <th className="pb-2 pr-3 text-right">Error</th>
              <th className="pb-2 pr-3 text-right">Fallback</th>
              <th className="pb-2 pr-3 text-right">p95 ms</th>
              <th className="pb-2 pr-3 text-right">Cost</th>
              <th className="pb-2 pr-3 text-right">Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => (
              <tr
                key={p.provider}
                className="border-b border-gray-100 last:border-0 dark:border-gray-800/60"
              >
                <td className="py-2.5 pr-3 font-semibold text-foreground">{p.provider}</td>
                <td className="py-2.5 pr-3 text-right">{p.totalRequests.toLocaleString()}</td>
                <td className="py-2.5 pr-3 text-right text-emerald-500">{fmtPct(p.successRate)}</td>
                <td className="py-2.5 pr-3 text-right text-red-500">{fmtPct(p.errorRate)}</td>
                <td className="py-2.5 pr-3 text-right">{fmtPct(p.fallbackRate)}</td>
                <td className="py-2.5 pr-3 text-right">{fmtMs(p.p95LatencyMs)}</td>
                <td className="py-2.5 pr-3 text-right text-amber-600">
                  {fmtUsd(p.estimatedCostUsd)}
                </td>
                <td className="py-2.5 pr-3 text-right">
                  <Badge
                    tone={
                      p.isHealthy
                        ? "bg-emerald-500/10 text-emerald-500"
                        : "bg-red-500/10 text-red-500"
                    }
                  >
                    {p.availabilityStatus}
                  </Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function CostView() {
  const { data, isLoading } = useAiCost(30);
  if (isLoading) return <Loading />;
  if (!data) return <Empty message="No cost telemetry yet." />;
  const maxFeature = Math.max(1, ...data.byFeature.map((b) => b.costUsd));
  const maxProvider = Math.max(1, ...data.byProvider.map((b) => b.costUsd));
  return (
    <div className="flex flex-col gap-5">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat
          label="Cost (30d)"
          value={fmtUsd(data.totalEstimatedCostUsd)}
          tone="text-amber-600"
          sub={data.isEstimatedCost ? "ESTIMATED USD — not billing" : "USD"}
        />
        <Stat
          label="Cost / execution"
          value={fmtUsd(data.costPerExecutionUsd)}
          sub={`per successful ${fmtUsd(data.costPerSuccessfulExecutionUsd)}`}
        />
        <Stat
          label="Tokens"
          value={data.totalTokens.toLocaleString()}
          sub={`${data.inputTokens.toLocaleString()} in / ${data.outputTokens.toLocaleString()} out`}
        />
        <Stat
          label="vs previous window"
          value={
            data.vsPreviousWindowPct != null
              ? `${data.vsPreviousWindowPct > 0 ? "+" : ""}${data.vsPreviousWindowPct}%`
              : NO_DATA
          }
          tone={
            data.vsPreviousWindowPct != null && data.vsPreviousWindowPct >= 20
              ? "text-red-500"
              : "text-foreground"
          }
          sub="equal 30-day look-back"
        />
      </div>

      {data.anomalies.length > 0 && (
        <Card title="Anomalies">
          <div className="flex flex-col gap-2">
            {data.anomalies.map((a, i) => (
              <div
                key={`${a.type}-${i}`}
                className="flex items-start gap-3 rounded-lg bg-amber-500/5 px-3 py-2 text-sm"
              >
                <Badge
                  tone={
                    a.severity === "warning"
                      ? "bg-amber-500/10 text-amber-500"
                      : "bg-sky-500/10 text-sky-500"
                  }
                >
                  {a.severity}
                </Badge>
                <span className="text-gray-700 dark:text-gray-300">{a.message}</span>
              </div>
            ))}
          </div>
        </Card>
      )}

      <Card title="Daily estimated cost" subtitle="ESTIMATED USD per day">
        <TrendChart
          points={toChartPoints(data.trend, "costUsd")}
          formatValue={fmtUsd}
          ariaLabel="Daily estimated AI cost over last 30 days"
        />
      </Card>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Card title="Cost by feature" subtitle="ESTIMATED USD">
          <div className="space-y-2">
            {data.byFeature.map((b) => (
              <BarRow
                key={b.featureKey}
                label={b.featureKey}
                value={b.costUsd}
                max={maxFeature}
                detail={fmtUsd(b.costUsd)}
              />
            ))}
            {data.byFeature.length === 0 && <Empty message="No spend recorded." />}
          </div>
        </Card>
        <Card title="Cost by provider" subtitle="ESTIMATED USD">
          <div className="space-y-2">
            {data.byProvider.map((b) => (
              <BarRow
                key={b.provider}
                label={b.provider}
                value={b.costUsd}
                max={maxProvider}
                detail={fmtUsd(b.costUsd)}
              />
            ))}
            {data.byProvider.length === 0 && <Empty message="No spend recorded." />}
          </div>
        </Card>
      </div>
    </div>
  );
}

function PerformanceView() {
  const { data, isLoading } = useAiPerformance(30);
  if (isLoading) return <Loading />;
  if (!data) return <Empty message="No performance telemetry yet." />;
  const o = data.overall;
  return (
    <div className="flex flex-col gap-5">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Avg latency" value={fmtMs(o.avgLatencyMs)} />
        <Stat label="p50" value={fmtMs(o.p50LatencyMs)} />
        <Stat
          label="p95"
          value={fmtMs(o.p95LatencyMs)}
          tone={o.p95LatencyMs > 5000 ? "text-red-500" : "text-foreground"}
        />
        <Stat label="p99" value={fmtMs(o.p99LatencyMs)} />
      </div>
      {data.abnormalLatencyIncrease && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-500/30 dark:bg-red-950/30 dark:text-red-300">
          {data.abnormalLatencyIncrease.message}
        </div>
      )}
      <Card title="Daily average latency" subtitle="ms per day">
        <TrendChart
          points={toChartPoints(data.dailyTrend, "avgLatencyMs")}
          formatValue={(v) => `${v} ms`}
          ariaLabel="Daily average latency over the last 30 days"
        />
      </Card>
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <LatencyTable title="By feature" rows={data.byFeature} />
        <LatencyTable title="By provider" rows={data.byProvider} />
        <LatencyTable title="By model" rows={data.byModel} />
      </div>
    </div>
  );
}

function LatencyTable({
  title,
  rows,
}: {
  title: string;
  rows: { name: string; avgLatencyMs: number; count: number; p95LatencyMs: number }[];
}) {
  return (
    <Card title={title}>
      {rows.length === 0 ? (
        <Empty message="No data." />
      ) : (
        <div className="space-y-2">
          {rows.map((r) => (
            <div key={r.name} className="flex items-center justify-between text-sm">
              <span className="max-w-[45%] truncate text-gray-700 dark:text-gray-300">
                {r.name}
              </span>
              <span className="text-xs text-gray-500 dark:text-gray-400">
                {r.count.toLocaleString()} · {fmtMs(r.avgLatencyMs)} · p95 {fmtMs(r.p95LatencyMs)}
              </span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

function ErrorsView() {
  const { data, isLoading } = useAiErrors(30);
  if (isLoading) return <Loading />;
  if (!data) return <Empty message="No error telemetry yet." />;
  const maxFailType = Math.max(1, ...data.failureTypeBreakdown.map((b) => b.count));
  return (
    <div className="flex flex-col gap-5">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat
          label="Errors (30d)"
          value={data.totalErrors.toLocaleString()}
          tone={data.totalErrors > 0 ? "text-red-500" : "text-emerald-500"}
        />
        <Stat label="Error rate" value={fmtPct(data.errorRate)} />
        <Stat
          label="Timeouts"
          value={data.timeoutCount.toLocaleString()}
          sub={fmtPct(data.timeoutRate)}
        />
        <Stat
          label="Fallbacks"
          value={data.fallbackCount.toLocaleString()}
          sub={fmtPct(data.fallbackRate)}
        />
      </div>
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Card title="Failure types">
          <div className="space-y-2">
            {data.failureTypeBreakdown.map((b) => (
              <BarRow key={b.failureType} label={b.failureType} value={b.count} max={maxFailType} />
            ))}
            {data.failureTypeBreakdown.length === 0 && (
              <Empty message="No failure types recorded." />
            )}
          </div>
        </Card>
        <Card
          title="Top fallback reasons"
          subtitle="Sanitized error messages from fallback executions"
        >
          <div className="flex flex-col gap-2">
            {data.fallbackReasons.map((r) => (
              <div
                key={r.reason}
                className="flex items-start justify-between gap-3 rounded-lg bg-gray-50 px-3 py-2 text-xs dark:bg-gray-800/60"
              >
                <span className="line-clamp-2 flex-1 text-gray-700 dark:text-gray-300">
                  {r.reason}
                </span>
                <span className="shrink-0 font-semibold text-foreground">{r.count}</span>
              </div>
            ))}
            {data.fallbackReasons.length === 0 && <Empty message="No fallback reasons recorded." />}
          </div>
        </Card>
      </div>
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <Card title="Errors by feature">
          <div className="space-y-1.5">
            {data.byFeature.map((b) => (
              <div key={b.featureKey} className="flex justify-between text-sm">
                <span className="truncate text-gray-700 dark:text-gray-300">{b.featureKey}</span>
                <span className="font-semibold text-foreground">{b.count}</span>
              </div>
            ))}
            {data.byFeature.length === 0 && <Empty message="No errors." />}
          </div>
        </Card>
        <Card title="Errors by provider">
          <div className="space-y-1.5">
            {data.byProvider.map((b) => (
              <div key={b.provider} className="flex justify-between text-sm">
                <span className="truncate text-gray-700 dark:text-gray-300">{b.provider}</span>
                <span className="font-semibold text-foreground">{b.count}</span>
              </div>
            ))}
            {data.byProvider.length === 0 && <Empty message="No errors." />}
          </div>
        </Card>
        <Card title="Errors by model">
          <div className="space-y-1.5">
            {data.byModel.map((b) => (
              <div key={b.modelName} className="flex justify-between text-sm">
                <span className="truncate text-gray-700 dark:text-gray-300">{b.modelName}</span>
                <span className="font-semibold text-foreground">{b.count}</span>
              </div>
            ))}
            {data.byModel.length === 0 && <Empty message="No errors." />}
          </div>
        </Card>
      </div>
    </div>
  );
}

function QualityView() {
  const { data, isLoading } = useAiQuality(180);
  if (isLoading) return <Loading />;
  if (!data) return <Empty message="No evaluations yet." />;
  return (
    <div className="flex flex-col gap-5">
      <Card
        title={`Quality by feature (${data.features.length})`}
        subtitle="Latest completed evaluation per feature — scores are per-category, not one universal number"
      >
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-left text-sm">
            <thead>
              <tr className="border-b border-gray-200 text-xs uppercase tracking-wide text-gray-500 dark:border-gray-800">
                <th className="pb-2 pr-3">Feature</th>
                <th className="pb-2 pr-3 text-right">Score</th>
                <th className="pb-2 pr-3 text-right">Pass rate</th>
                <th className="pb-2 pr-3">Dataset</th>
                <th className="pb-2 pr-3">Provider / Model</th>
                <th className="pb-2 pr-3 text-right">Completed</th>
              </tr>
            </thead>
            <tbody>
              {data.features.map((f) => (
                <tr
                  key={f.runId}
                  className="border-b border-gray-100 last:border-0 dark:border-gray-800/60"
                >
                  <td className="py-2.5 pr-3">
                    <div className="font-semibold text-foreground">
                      {f.featureName || f.featureId}
                    </div>
                    <div className="text-[11px] text-gray-500">{f.category}</div>
                  </td>
                  <td className="py-2.5 pr-3 text-right text-foreground">{f.score}</td>
                  <td className="py-2.5 pr-3 text-right">{(f.passRate * 100).toFixed(1)}%</td>
                  <td className="py-2.5 pr-3 font-mono text-xs text-gray-600 dark:text-gray-400">
                    {f.datasetKey ?? NO_DATA}
                  </td>
                  <td className="py-2.5 pr-3 text-xs text-gray-600 dark:text-gray-400">
                    {f.provider} / {f.modelName}
                  </td>
                  <td className="py-2.5 pr-3 text-right text-xs text-gray-500">
                    {fmtDate(f.completedAt)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <Card title="Evaluator taxonomy" subtitle="How metrics are judged">
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {Object.entries(data.evaluatorTypes).map(([key, label]) => (
            <div key={key} className="rounded-lg bg-gray-50 px-3 py-2 dark:bg-gray-800/60">
              <div className="font-mono text-xs text-foreground">{key}</div>
              <div className="mt-0.5 text-xs text-gray-600 dark:text-gray-400">{label}</div>
            </div>
          ))}
        </div>
      </Card>
      {data.metrics.length > 0 && (
        <Card title={`Metric catalog (${data.metrics.length})`}>
          <div className="flex flex-wrap gap-2">
            {data.metrics.map((m) => (
              <span
                key={m.metricKey}
                className="inline-flex items-center gap-2 rounded-full bg-gray-50 px-3 py-1 text-xs text-gray-700 dark:bg-gray-800/60 dark:text-gray-300"
              >
                <span className="font-mono">{m.metricKey}</span>
                <span className="text-gray-400">·</span>
                {m.name}
              </span>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}

function DriftView() {
  const { data, isLoading } = useAiDrift();
  if (isLoading) return <Loading />;
  const rows = data ?? [];
  if (rows.length === 0) return <Empty message="No drift measurements yet." />;
  return (
    <Card
      title={`Drift status (${rows.length})`}
      subtitle="Derived from Phase 17 measurements — not a new drift engine"
    >
      <DriftTable rows={rows} />
    </Card>
  );
}

function DriftTable({ rows }: { rows: AiDriftRowValue[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[720px] text-left text-sm">
        <thead>
          <tr className="border-b border-gray-200 text-xs uppercase tracking-wide text-gray-500 dark:border-gray-800">
            <th className="pb-2 pr-3">Model</th>
            <th className="pb-2 pr-3">Metric</th>
            <th className="pb-2 pr-3 text-right">Value</th>
            <th className="pb-2 pr-3 text-right">Baseline</th>
            <th className="pb-2 pr-3">Threshold</th>
            <th className="pb-2 pr-3 text-right">Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr
              key={`${r.modelName}-${r.metricName}-${i}`}
              className="border-b border-gray-100 last:border-0 dark:border-gray-800/60"
            >
              <td className="py-2.5 pr-3">
                <div className="font-semibold text-foreground">{r.modelName}</div>
                <div className="text-[11px] text-gray-500">{r.modelVersion}</div>
              </td>
              <td className="py-2.5 pr-3 font-mono text-xs text-gray-600 dark:text-gray-400">
                {r.metricName}
              </td>
              <td className="py-2.5 pr-3 text-right">{r.value != null ? r.value : NO_DATA}</td>
              <td className="py-2.5 pr-3 text-right text-gray-600 dark:text-gray-400">
                {r.baselineValue != null ? r.baselineValue : NO_DATA}
              </td>
              <td className="py-2.5 pr-3 text-xs text-gray-600 dark:text-gray-400">
                {r.thresholdMin != null || r.thresholdMax != null
                  ? `${r.thresholdMin ?? "−∞"} … ${r.thresholdMax ?? "+∞"}${r.thresholdBreached ? " (breached)" : ""}`
                  : NO_DATA}
              </td>
              <td className="py-2.5 pr-3 text-right">
                <Badge tone={driftTone[r.status] ?? "bg-gray-500/10 text-gray-500"}>
                  {r.status}
                </Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PromptsView() {
  const { data, isLoading } = useAiPrompts(90);
  if (isLoading) return <Loading />;
  const rows = data ?? [];
  if (rows.length === 0) return <Empty message="No prompts registered yet." />;
  return (
    <Card
      title={`Prompt health (${rows.length})`}
      subtitle="Active/previous versions + latest evaluation"
    >
      <div className="overflow-x-auto">
        <table className="w-full min-w-[760px] text-left text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-xs uppercase tracking-wide text-gray-500 dark:border-gray-800">
              <th className="pb-2 pr-3">Prompt</th>
              <th className="pb-2 pr-3 text-right">Versions</th>
              <th className="pb-2 pr-3 text-right">Active</th>
              <th className="pb-2 pr-3 text-right">Eval score</th>
              <th className="pb-2 pr-3 text-right">Score Δ</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => {
              const ms = p.latestEvaluationMetricScores ?? {};
              const firstMetric = Object.entries(ms)[0];
              return (
                <tr
                  key={p.promptKey}
                  className="border-b border-gray-100 last:border-0 dark:border-gray-800/60"
                >
                  <td className="py-2.5 pr-3">
                    <div className="font-semibold text-foreground">{p.name || p.promptKey}</div>
                    <div className="text-[11px] text-gray-500">
                      {p.featureId ? `${p.featureId} · ` : ""}
                      model {p.defaultModel}
                    </div>
                  </td>
                  <td className="py-2.5 pr-3 text-right">{p.versionCount}</td>
                  <td className="py-2.5 pr-3 text-right">
                    v{p.activeVersion ?? NO_DATA}
                    {p.previousVersion != null ? ` (prev v${p.previousVersion})` : ""}
                  </td>
                  <td className="py-2.5 pr-3 text-right">
                    {p.latestEvaluationScore != null ? p.latestEvaluationScore.toFixed(4) : NO_DATA}
                  </td>
                  <td className="py-2.5 pr-3 text-right text-xs">
                    {firstMetric ? `${firstMetric[0]}=${firstMetric[1]}` : NO_DATA}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Alerts
// ---------------------------------------------------------------------------

function AlertsView({ highlightKey }: { highlightKey: string | null }) {
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [severityFilter, setSeverityFilter] = useState<string>("");
  const { data: alerts, isLoading: alertsLoading } = useAiAlerts({
    status: statusFilter || undefined,
    severity: severityFilter || undefined,
  });
  const { data: rules, isLoading: rulesLoading } = useAiAlertRules();
  const { acknowledge, resolve, suppress } = useAlertLifecycle();
  const runEvaluate = useEvaluateAiAlerts();
  const createRule = useCreateAiAlertRule();
  const updateRule = useUpdateAiAlertRule();
  const deleteRule = useDeleteAiAlertRule();
  const [editorOpen, setEditorOpen] = useState(false);
  const [editingRule, setEditingRule] = useState<AiAlertRule | null>(null);

  const openCreate = () => {
    setEditingRule(null);
    setEditorOpen(true);
  };
  const openEdit = (rule: AiAlertRule) => {
    setEditingRule(rule);
    setEditorOpen(true);
  };

  const pendingLifecycle = acknowledge.isPending || resolve.isPending || suppress.isPending;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <Select value={statusFilter} onValueChange={(v) => setStatusFilter(v)}>
            <SelectTrigger className="w-40">
              <SelectValue placeholder="All statuses" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="">All statuses</SelectItem>
              <SelectItem value="triggered">Triggered</SelectItem>
              <SelectItem value="acknowledged">Acknowledged</SelectItem>
              <SelectItem value="resolved">Resolved</SelectItem>
              <SelectItem value="suppressed">Suppressed</SelectItem>
            </SelectContent>
          </Select>
          <Select value={severityFilter} onValueChange={(v) => setSeverityFilter(v)}>
            <SelectTrigger className="w-40">
              <SelectValue placeholder="All severities" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="">All severities</SelectItem>
              <SelectItem value="info">Info</SelectItem>
              <SelectItem value="warning">Warning</SelectItem>
              <SelectItem value="critical">Critical</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => runEvaluate.mutate()}
            disabled={runEvaluate.isPending}
          >
            {runEvaluate.isPending ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <BellRing className="size-3.5" />
            )}
            Evaluate now
          </Button>
          <Button
            size="sm"
            className="bg-orange-600 text-white hover:bg-orange-700"
            onClick={openCreate}
          >
            + New rule
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <div>
          <h3 className="mb-3 font-display text-sm font-bold text-foreground">
            Alerts {(alerts ?? []).length > 0 ? `(${(alerts ?? []).length})` : ""}
          </h3>
          {alertsLoading ? (
            <Loading label="Loading alerts…" />
          ) : (alerts ?? []).length === 0 ? (
            <Empty message="No alerts match the current filters." />
          ) : (
            <div className="flex max-h-[560px] flex-col gap-3 overflow-y-auto pr-1">
              {(alerts ?? []).map((a) => (
                <AlertCard
                  key={a.id}
                  alert={a}
                  highlight={highlightKey === a.alertKey}
                  lifecycleBusy={pendingLifecycle}
                  onAcknowledge={() => acknowledge.mutate({ id: a.id })}
                  onResolve={() => resolve.mutate({ id: a.id })}
                  onSuppress={() => suppress.mutate({ id: a.id })}
                />
              ))}
            </div>
          )}
        </div>

        <div>
          <h3 className="mb-3 font-display text-sm font-bold text-foreground">
            Rules {(rules ?? []).length > 0 ? `(${(rules ?? []).length})` : ""}
          </h3>
          {rulesLoading ? (
            <Loading label="Loading rules…" />
          ) : (rules ?? []).length === 0 ? (
            <Empty message="No alert rules yet. Create one to start watching a metric." />
          ) : (
            <div className="flex max-h-[560px] flex-col gap-3 overflow-y-auto pr-1">
              {(rules ?? []).map((r) => (
                <RuleCard
                  key={r.id}
                  rule={r}
                  onEdit={() => openEdit(r)}
                  onDelete={() => deleteRule.mutate(r.id)}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      {editorOpen && (
        <RuleEditor
          initial={editingRule}
          onClose={() => setEditorOpen(false)}
          onSave={(payload) => {
            if (editingRule) {
              updateRule.mutate(
                { id: editingRule.id, payload },
                { onSettled: () => setEditorOpen(false) }
              );
            } else {
              createRule.mutate(payload, { onSettled: () => setEditorOpen(false) });
            }
          }}
        />
      )}
    </div>
  );
}

function AlertCard({
  alert,
  highlight,
  lifecycleBusy,
  onAcknowledge,
  onResolve,
  onSuppress,
}: {
  alert: AiAlert;
  highlight: boolean;
  lifecycleBusy: boolean | undefined;
  onAcknowledge: () => void;
  onResolve: () => void;
  onSuppress: () => void;
}) {
  const actionable = alert.status !== "resolved";
  return (
    <div
      className={cn(
        "rounded-xl border border-gray-200 bg-card p-4 dark:border-gray-800",
        highlight && "ring-2 ring-orange-500"
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <ShieldAlert className="size-4 shrink-0 text-gray-400" />
          <span className="font-display text-sm font-bold text-foreground">{alert.title}</span>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Badge tone={severityTone[alert.severity] ?? "bg-gray-500/10 text-gray-500"}>
            {alert.severity}
          </Badge>
          <Badge tone={alertStatusTone[alert.status] ?? "bg-gray-500/10 text-gray-500"}>
            {alert.status}
          </Badge>
        </div>
      </div>
      <p className="mt-2 text-sm leading-relaxed text-gray-600 dark:text-gray-400">
        {alert.message}
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
        <span>
          {alert.ruleKey ?? alert.alertType} · {alert.metricName}= {alert.metricValue} vs{" "}
          {alert.thresholdValue}
        </span>
        {alert.featureId && <span>feature {alert.featureId}</span>}
        {alert.provider && <span>provider {alert.provider}</span>}
        {alert.modelName && <span>model {alert.modelName}</span>}
        <span>{fmtDate(alert.triggeredAt)}</span>
      </div>
      {actionable && (
        <div className="mt-3 flex flex-wrap gap-2">
          {alert.status === "triggered" && (
            <Button size="sm" variant="outline" onClick={onAcknowledge} disabled={lifecycleBusy}>
              Acknowledge
            </Button>
          )}
          <Button size="sm" variant="outline" onClick={onResolve} disabled={lifecycleBusy}>
            Resolve
          </Button>
          <Button size="sm" variant="ghost" onClick={onSuppress} disabled={lifecycleBusy}>
            Suppress
          </Button>
        </div>
      )}
      {alert.resolutionNote && (
        <div className="mt-2 rounded-lg bg-gray-50 px-3 py-2 text-xs text-gray-600 dark:bg-gray-800/60 dark:text-gray-400">
          {alert.resolutionNote}
        </div>
      )}
    </div>
  );
}

function RuleCard({
  rule,
  onEdit,
  onDelete,
}: {
  rule: AiAlertRule;
  onEdit: () => void;
  onDelete: () => void;
}) {
  return (
    <div className="rounded-xl border border-gray-200 bg-card p-4 dark:border-gray-800">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-display text-sm font-bold text-foreground">{rule.name}</span>
            <Badge
              tone={
                rule.isEnabled
                  ? "bg-emerald-500/10 text-emerald-500"
                  : "bg-gray-500/10 text-gray-500"
              }
            >
              {rule.isEnabled ? "enabled" : "disabled"}
            </Badge>
          </div>
          <div className="mt-0.5 font-mono text-[11px] text-gray-500">{rule.ruleKey}</div>
        </div>
        <Badge tone={severityTone[rule.severity] ?? "bg-gray-500/10 text-gray-500"}>
          {rule.severity}
        </Badge>
      </div>
      <div className="mt-2 text-sm text-foreground">
        {rule.metricDisplay} {rule.operatorDisplay} {rule.thresholdValue}
      </div>
      <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
        {rule.alertTypeDisplay} · lookback {rule.durationMinutes} min · {rule.consecutiveChecks}{" "}
        consecutive · cooldown {rule.cooldownMinutes} min
        {rule.featureId ? ` · ${rule.featureId}` : ""}
        {rule.provider || rule.modelName
          ? ` · ${[rule.provider, rule.modelName].filter(Boolean).join("/")}`
          : ""}
      </div>
      <div className="mt-2 flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
        <span>
          {rule.breachCount > 0 ? `breach streak ${rule.breachCount}` : "no active breach"}
          {rule.lastMetricValue != null ? ` · last ${rule.lastMetricValue}` : ""}
        </span>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={onEdit}
            className="font-semibold text-orange-600 hover:underline"
          >
            Edit
          </button>
          <button
            type="button"
            onClick={onDelete}
            className="font-semibold text-red-500 hover:underline"
          >
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}

const METRIC_OPTIONS = [
  ["error_rate", "Error rate"],
  ["timeout_rate", "Timeout rate"],
  ["fallback_rate", "Fallback rate"],
  ["success_rate", "Success rate"],
  ["avg_latency", "Avg latency (ms)"],
  ["p95_latency", "P95 latency (ms)"],
  ["daily_cost", "Daily est. cost (USD)"],
  ["cost_per_execution", "Cost / execution (USD)"],
  ["evaluation_score", "Evaluation score"],
  ["drift_breach", "Drift breach count"],
] as const;

const ALERT_TYPE_OPTIONS = [
  ["reliability", "Reliability"],
  ["performance", "Performance"],
  ["quality", "Quality"],
  ["cost", "Cost"],
  ["drift", "Drift"],
  ["availability", "Availability"],
] as const;

function RuleEditor({
  initial,
  onClose,
  onSave,
}: {
  initial: AiAlertRule | null;
  onClose: () => void;
  onSave: (payload: NewAiAlertRule) => void;
}) {
  const [form, setForm] = useState<NewAiAlertRule>({
    ruleKey: initial?.ruleKey ?? "",
    name: initial?.name ?? "",
    description: initial?.description ?? "",
    alertType: initial?.alertType ?? "reliability",
    metric: initial?.metric ?? "error_rate",
    operator: initial?.operator ?? "gt",
    thresholdValue: initial?.thresholdValue ?? 5,
    featureId: initial?.featureId ?? "",
    provider: initial?.provider ?? "",
    modelName: initial?.modelName ?? "",
    durationMinutes: initial?.durationMinutes ?? 5,
    consecutiveChecks: initial?.consecutiveChecks ?? 1,
    cooldownMinutes: initial?.cooldownMinutes ?? 60,
    severity: initial?.severity ?? "warning",
    isEnabled: initial?.isEnabled ?? true,
    notifyAdmins: initial?.notifyAdmins ?? true,
  });

  const set = <K extends keyof NewAiAlertRule>(key: K, value: NewAiAlertRule[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const canSave =
    form.ruleKey.trim() !== "" && form.name.trim() !== "" && Number.isFinite(form.thresholdValue);

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/50 p-4 pt-16"
      role="dialog"
      aria-modal="true"
      aria-label="Alert rule editor"
    >
      <div className="w-full max-w-2xl rounded-2xl border border-gray-200 bg-card p-5 dark:border-gray-800">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="font-display text-lg font-bold text-foreground">
            {initial ? `Edit rule — ${initial.ruleKey}` : "New alert rule"}
          </h3>
          <Button variant="ghost" size="sm" onClick={onClose}>
            Close
          </Button>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <Label>Name</Label>
            <Input
              value={form.name}
              onChange={(e) => set("name", e.target.value)}
              placeholder="e.g. Copilot error rate"
            />
          </div>
          <div>
            <Label>Rule key</Label>
            <Input
              value={form.ruleKey}
              onChange={(e) => set("ruleKey", e.target.value)}
              placeholder="e.g. copilot_error_rate"
              disabled={initial != null}
            />
          </div>
          <div>
            <Label>Description</Label>
            <Input
              value={form.description}
              onChange={(e) => set("description", e.target.value)}
              placeholder="Optional"
            />
          </div>
          <div>
            <Label>Alert type</Label>
            <Select value={form.alertType} onValueChange={(v) => set("alertType", v)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ALERT_TYPE_OPTIONS.map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Metric</Label>
            <Select value={form.metric} onValueChange={(v) => set("metric", v)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {METRIC_OPTIONS.map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Operator</Label>
            <Select value={form.operator} onValueChange={(v) => set("operator", v)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="gt">&gt;</SelectItem>
                <SelectItem value="gte">&gt;=</SelectItem>
                <SelectItem value="lt">&lt;</SelectItem>
                <SelectItem value="lte">&lt;=</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Threshold</Label>
            <Input
              type="number"
              step="any"
              value={form.thresholdValue}
              onChange={(e) => set("thresholdValue", Number(e.target.value))}
            />
          </div>
          <div>
            <Label>Severity</Label>
            <Select value={form.severity} onValueChange={(v) => set("severity", v)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="info">Info</SelectItem>
                <SelectItem value="warning">Warning</SelectItem>
                <SelectItem value="critical">Critical</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Scope — feature</Label>
            <Input
              value={form.featureId}
              onChange={(e) => set("featureId", e.target.value)}
              placeholder="e.g. room.copilot (blank = all)"
            />
          </div>
          <div>
            <Label>Scope — provider</Label>
            <Input
              value={form.provider}
              onChange={(e) => set("provider", e.target.value)}
              placeholder="Optional"
            />
          </div>
          <div>
            <Label>Scope — model</Label>
            <Input
              value={form.modelName}
              onChange={(e) => set("modelName", e.target.value)}
              placeholder="Optional"
            />
          </div>
          <div>
            <Label>Lookback (minutes)</Label>
            <Input
              type="number"
              min={1}
              value={form.durationMinutes}
              onChange={(e) => set("durationMinutes", Number(e.target.value))}
            />
          </div>
          <div>
            <Label>Consecutive checks</Label>
            <Input
              type="number"
              min={1}
              value={form.consecutiveChecks}
              onChange={(e) => set("consecutiveChecks", Number(e.target.value))}
            />
          </div>
          <div>
            <Label>Cooldown (minutes)</Label>
            <Input
              type="number"
              min={0}
              value={form.cooldownMinutes}
              onChange={(e) => set("cooldownMinutes", Number(e.target.value))}
            />
          </div>
          <div className="flex items-end gap-4 pb-1">
            <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
              <input
                type="checkbox"
                checked={form.isEnabled}
                onChange={(e) => set("isEnabled", e.target.checked)}
              />
              Enabled
            </label>
            <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
              <input
                type="checkbox"
                checked={form.notifyAdmins}
                onChange={(e) => set("notifyAdmins", e.target.checked)}
              />
              Notify admins
            </label>
          </div>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={!canSave}
            onClick={() => onSave(form)}
            className="bg-orange-600 text-white hover:bg-orange-700"
          >
            {initial ? "Save changes" : "Create rule"}
          </Button>
        </div>
      </div>
    </div>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return (
    <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">
      {children}
    </label>
  );
}

interface AiDriftRowValue {
  modelName: string;
  modelVersion: string;
  metricName: string;
  value: number | null;
  baselineValue: number | null;
  thresholdMin: number | null;
  thresholdMax: number | null;
  thresholdBreached: boolean;
  status: string;
  windowEnd: string | null;
  lastChecked: string | null;
}

// ---------------------------------------------------------------------------
// Panel root
// ---------------------------------------------------------------------------

export default function AdminAiPanel() {
  const [searchParams] = useSearchParams();
  const requested = searchParams.get("view");
  const [view, setView] = useState<AiView>(
    AI_VIEWS.includes(requested as AiView) ? (requested as AiView) : "overview"
  );
  const highlightKey = useMemo(() => searchParams.get("alert"), [searchParams]);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap gap-1 rounded-xl bg-gray-50 p-1 dark:bg-gray-800">
        {AI_VIEWS.map((v) => (
          <button
            key={v}
            type="button"
            className={cn(
              "rounded-lg px-3.5 py-1.5 text-sm font-medium capitalize transition-colors",
              view === v
                ? "bg-card text-foreground shadow-sm"
                : "text-gray-600 hover:text-foreground dark:text-gray-400"
            )}
            onClick={() => setView(v)}
          >
            {v}
          </button>
        ))}
      </div>
      <div>
        <h2 className="font-display text-lg font-bold text-foreground">AI Intelligence</h2>
        <p className="mt-0.5 text-sm text-gray-600 dark:text-gray-400">
          Administrators only · costs are ESTIMATED USD from execution telemetry — never billing.
        </p>
      </div>

      {view === "overview" && <OverviewView />}
      {view === "features" && <FeaturesView />}
      {view === "models" && <ModelsView />}
      {view === "providers" && <ProvidersView />}
      {view === "cost" && <CostView />}
      {view === "performance" && <PerformanceView />}
      {view === "errors" && <ErrorsView />}
      {view === "quality" && <QualityView />}
      {view === "drift" && <DriftView />}
      {view === "prompts" && <PromptsView />}
      {view === "alerts" && <AlertsView highlightKey={highlightKey} />}
    </div>
  );
}
