import { useState } from "react";
import {
  BadgeCheck,
  Bot,
  Check,
  ChevronDown,
  Loader2,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import useListingAutopilot from "../../hooks/useListingAutopilot";
import type {
  AutopilotAnalysis,
  AutopilotProposal,
  AutopilotProposalStatus,
} from "../../services/listingAutopilotService";
import { cn } from "../../lib/utils";
import { Button } from "../ui/button";

const TYPE_LABEL: Record<string, string> = {
  TITLE_UPDATE: "Title",
  DESCRIPTION_UPDATE: "Description",
  AMENITY_UPDATE: "Amenities",
  PHOTO_RECOMMENDATION: "Photos",
  PRICE_UPDATE: "Price",
  LISTING_RENEWAL: "Renewal",
};

const STATUS_LABEL: Record<AutopilotProposalStatus, string> = {
  pending: "Awaiting your approval",
  approved: "Approved — applying",
  applied: "Applied",
  rejected: "Rejected",
  expired: "Expired",
  failed: "Apply failed",
};

const STATUS_BADGE: Record<AutopilotProposalStatus, string> = {
  pending: "bg-amber-500/10 text-amber-700 dark:text-amber-400",
  approved: "bg-blue-500/10 text-blue-700 dark:text-blue-400",
  applied: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
  rejected: "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400",
  expired: "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400",
  failed: "bg-rose-500/10 text-rose-700 dark:text-rose-400",
};

const STATUS_FILTERS: (AutopilotProposalStatus | "")[] = [
  "",
  "pending",
  "applied",
  "rejected",
  "failed",
];

/**
 * Phase 19.3 AI Listing Autopilot panel (landlord).
 *
 * Every Friday a Celery run analyzes the landlord's listings and mints typed,
 * grounded proposals (title/description/amenities/photos/price/renewal). Each
 * card is backed by deterministic analysis — scores from the listing-quality
 * and property-intelligence engines, price from the price engine. Landlords
 * approve to apply exactly once (replay-safe server-side) or reject; rejecting
 * frees the slot for next week. The AI never self-approves.
 */
export default function AutopilotPanel() {
  const {
    overview,
    proposals,
    analyses,
    loading,
    busyKey,
    error,
    lastAction,
    reload,
    setStatusFilter,
    approve,
    reject,
    approveAll,
  } = useListingAutopilot();

  const [rejectKey, setRejectKey] = useState<string | null>(null);
  const [filter, setFilter] = useState<AutopilotProposalStatus | "">("");
  const [showAnalyses, setShowAnalyses] = useState(false);

  const pendingCount = proposals.filter((p) => p.status === "pending").length;

  const onApprove = async (key: string) => {
    try {
      await approve(key);
    } catch {
      // surfaced via state.error
    }
  };

  const onReject = async (key: string, reason?: string) => {
    setRejectKey(null);
    try {
      await reject(key, reason);
    } catch {
      // surfaced via state.error
    }
  };

  const onFilterChange = (value: AutopilotProposalStatus | "") => {
    setFilter(value);
    setStatusFilter(value);
  };

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900">
      {/* Header */}
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
            <Sparkles className="size-4" />
          </div>
          <div>
            <h3 className="font-display text-sm font-bold text-foreground">Listing Autopilot</h3>
            <p className="text-[11px] text-gray-500 dark:text-gray-400">
              Weekly, grounded recommendations for your listings
            </p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          {overview?.enabled ? (
            <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-600 dark:text-emerald-400">
              live
            </span>
          ) : (
            <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] font-semibold text-amber-600 dark:text-amber-400">
              feature off
            </span>
          )}
          <button
            type="button"
            onClick={() => void reload()}
            disabled={loading}
            aria-label="Refresh autopilot"
            className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600 disabled:opacity-50 dark:hover:bg-gray-800"
          >
            <RefreshCw className={cn("size-3.5", loading && "animate-spin")} />
          </button>
        </div>
      </div>

      {!overview?.enabled && !loading && (
        <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] leading-relaxed text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300">
          The autopilot isn&apos;t enabled yet — it activates behind the feature flag{" "}
          <code>ai.listing_autopilot</code>. What you see here could be from an earlier run.
        </div>
      )}

      {error && (
        <div className="mb-3 rounded-lg bg-rose-50 px-3 py-2 text-[11px] leading-relaxed text-rose-700 dark:bg-rose-950/40 dark:text-rose-300">
          {error}
        </div>
      )}

      {lastAction && !error && (
        <div className="mb-3 text-[11px] text-gray-500 dark:text-gray-400">{lastAction}</div>
      )}

      {/* Summary */}
      <div className="mb-3 grid grid-cols-3 gap-2">
        <SummaryStat label="Pending" value={pendingCount} tone="amber" />
        <SummaryStat
          label="Applied"
          value={proposals.filter((p) => p.status === "applied").length}
          tone="emerald"
        />
        <SummaryStat label="Listings scored" value={analyses.length} tone="indigo" />
      </div>

      {/* Toolbar */}
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap gap-1">
          {STATUS_FILTERS.map((s) => (
            <button
              key={s || "all"}
              type="button"
              onClick={() => onFilterChange(s)}
              className={cn(
                "rounded-full px-2.5 py-1 text-[10px] font-semibold",
                filter === s
                  ? "bg-emerald-600 text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300"
              )}
            >
              {s === "" ? "All" : STATUS_LABEL[s]}
            </button>
          ))}
        </div>
        {pendingCount > 0 && (
          <Button
            type="button"
            size="sm"
            className="h-7 text-[11px] bg-emerald-600 hover:bg-emerald-700"
            disabled={busyKey !== null}
            onClick={() => void approveAll()}
          >
            {busyKey === "all" ? (
              <Loader2 className="size-3 animate-spin" />
            ) : (
              <Check className="size-3" />
            )}
            Approve all ({pendingCount})
          </Button>
        )}
        <button
          type="button"
          onClick={() => setShowAnalyses((v) => !v)}
          className="flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] font-semibold text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
        >
          Weekly snapshots
          <ChevronDown
            className={cn("size-3 transition-transform", showAnalyses && "rotate-180")}
          />
        </button>
      </div>

      {/* Analyses (collapsible) */}
      {showAnalyses && (
        <div className="mb-3 space-y-1.5">
          {analyses.length === 0 && (
            <p className="text-[11px] text-gray-400">No weekly snapshots yet.</p>
          )}
          {analyses.slice(0, 6).map((a) => (
            <AnalysisRow key={a.id} a={a} />
          ))}
        </div>
      )}

      {/* Proposals */}
      {loading ? (
        <div className="flex items-center gap-2 py-6 text-xs text-gray-500">
          <Loader2 className="size-3.5 animate-spin" />
          Loading recommendations…
        </div>
      ) : proposals.length === 0 ? (
        <div className="rounded-lg bg-gray-50 px-3 py-5 text-center text-xs text-gray-500 dark:bg-gray-800/60 dark:text-gray-400">
          <Bot className="mx-auto mb-1 size-5 text-gray-300 dark:text-gray-600" />
          No {filter ? `${STATUS_LABEL[filter].toLowerCase()} ` : ""}recommendations right now.
        </div>
      ) : (
        <div className="space-y-2">
          {proposals.map((p) => (
            <ProposalCard
              key={p.key}
              p={p}
              busy={busyKey === p.key}
              rejectKey={rejectKey}
              onApprove={onApprove}
              onReject={onReject}
              onBeginReject={() => setRejectKey(p.key)}
              onCancelReject={() => setRejectKey(null)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function SummaryStat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "amber" | "emerald" | "indigo";
}) {
  const tones = {
    amber: "bg-amber-500/10 text-amber-700 dark:text-amber-400",
    emerald: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
    indigo: "bg-indigo-500/10 text-indigo-700 dark:text-indigo-400",
  };
  return (
    <div className={cn("rounded-lg px-3 py-2", tones[tone])}>
      <div className="text-lg font-bold leading-none">{value}</div>
      <div className="mt-0.5 text-[10px] font-semibold opacity-80">{label}</div>
    </div>
  );
}

function AnalysisRow({ a }: { a: AutopilotAnalysis }) {
  return (
    <div className="flex items-center justify-between gap-2 rounded-lg border border-gray-100 px-3 py-1.5 text-[11px] dark:border-gray-800">
      <div className="min-w-0">
        <span className="font-bold text-foreground">#{a.room_id}</span>
        <span className="ml-1.5 text-gray-500">{a.week_key}</span>
      </div>
      {a.quality_score != null && (
        <span className="shrink-0 font-semibold text-emerald-600 dark:text-emerald-400">
          {Math.round(a.quality_score)}/100
        </span>
      )}
      {a.price_direction !== "hold" && (
        <span className="shrink-0 text-gray-500">price: {a.price_direction}</span>
      )}
    </div>
  );
}

function ProposalCard({
  p,
  busy,
  rejectKey,
  onApprove,
  onReject,
  onBeginReject,
  onCancelReject,
}: {
  p: AutopilotProposal;
  busy: boolean;
  rejectKey: string | null;
  onApprove: (key: string) => Promise<void>;
  onReject: (key: string, reason?: string) => Promise<void>;
  onBeginReject: () => void;
  onCancelReject: () => void;
}) {
  const pending = p.status === "pending";
  return (
    <div className="rounded-xl border border-gray-200 p-3 dark:border-gray-700 dark:bg-gray-900">
      <div className="mb-1 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <ShieldCheck className="size-3.5 shrink-0 text-emerald-600 dark:text-emerald-400" />
            <span className="rounded-full bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-bold text-emerald-700 dark:text-emerald-400">
              {TYPE_LABEL[p.type] ?? p.type}
            </span>
            {p.room_id != null && (
              <span className="text-[10px] text-gray-400">Listing #{p.room_id}</span>
            )}
          </div>
          <p className="mt-0.5 text-[11px] text-gray-600 dark:text-gray-400">{p.summary}</p>
        </div>
        <span
          className={cn(
            "shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold",
            STATUS_BADGE[p.status]
          )}
        >
          {STATUS_LABEL[p.status] ?? p.status}
        </span>
      </div>

      {p.status === "failed" && p.application_result && (
        <p className="mb-1 text-[10px] text-rose-600 dark:text-rose-400">
          {String(p.application_result.error ?? "apply failed")}
        </p>
      )}
      {p.rejection_reason && (
        <p className="mb-1 text-[10px] text-gray-500">Reason: {p.rejection_reason}</p>
      )}

      {pending && (
        <div className="mt-2 flex items-center justify-end gap-1.5">
          {rejectKey === p.key ? (
            <>
              <input
                autoFocus
                placeholder="Reason (optional)"
                onKeyDown={(e) => {
                  if (e.key === "Escape") onCancelReject();
                  if (e.key === "Enter") void onReject(p.key, e.currentTarget.value || undefined);
                }}
                onBlur={onCancelReject}
                className="h-7 min-w-0 flex-1 rounded-lg border border-gray-300 px-2 text-[11px] focus:outline-none focus:ring-2 focus:ring-rose-500/40 dark:border-gray-600 dark:bg-gray-900"
                aria-label="Reject reason"
              />
              <Button
                size="sm"
                variant="outline"
                className="h-7 px-2 text-[10px] text-rose-600 dark:text-rose-400"
                onClick={() => void onReject(p.key)}
              >
                <X className="size-3" />
                Reject
              </Button>
            </>
          ) : (
            <>
              <Button
                size="sm"
                variant="outline"
                className="h-7 px-2 text-[10px] text-rose-600 dark:text-rose-400"
                onClick={onBeginReject}
                disabled={busy}
              >
                <X className="size-3" />
                Reject
              </Button>
              <Button
                size="sm"
                className="h-7 px-2 text-[10px] bg-emerald-600 hover:bg-emerald-700"
                onClick={() => void onApprove(p.key)}
                disabled={busy}
              >
                {busy ? (
                  <Loader2 className="size-3 animate-spin" />
                ) : (
                  <BadgeCheck className="size-3" />
                )}
                Approve &amp; apply
              </Button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
