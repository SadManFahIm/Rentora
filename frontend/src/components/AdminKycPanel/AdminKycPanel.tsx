import { useState, type Dispatch, type SetStateAction } from "react";
import {
  AlertTriangle,
  BadgeCheck,
  Check,
  Clock,
  ExternalLink,
  History,
  Loader2,
  ShieldCheck,
  ShieldOff,
  TrendingDown,
  Users,
  X,
} from "lucide-react";
import { toast } from "sonner";
import {
  useKycAuditTrail,
  useKycSla,
  usePendingKycApplications,
  usePendingTenantKycApplications,
  useReviewKycApplication,
  useReviewTenantKycApplication,
} from "../../hooks/useKyc";
import { kycService } from "../../services/kycService";
import { getApiErrorMessage } from "../../services/errors";
import type { KycSla, TenantKycApplication, TenantKycDecision } from "../../types";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { cn } from "../../lib/utils";

const docStatusClasses: Record<string, string> = {
  pending: "bg-amber-500/10 text-amber-500",
  approved: "bg-emerald-500/10 text-emerald-500",
  rejected: "bg-red-500/10 text-red-500",
};

/** Relative-ish, readable timestamp (e.g. "5 Jan, 14:32"). */
function formatWhen(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

/** Queue-health strip: pending volume, decision speed, and the 7-day trend. */
function SlaStats() {
  const { data: sla, isLoading } = useKycSla();

  const breachLabels: Record<string, { label: string; icon: typeof AlertTriangle }> = {
    oldest_pending: {
      label: "Application waiting >48h",
      icon: AlertTriangle,
    },
    trend_negative: {
      label: "Decisions down vs last week",
      icon: TrendingDown,
    },
  };

  const cards = [
    {
      icon: Users,
      label: "Pending applications",
      value: sla?.pendingCount ?? "—",
      sub:
        sla?.pendingOldestHours != null
          ? `oldest waiting ${formatHours(sla.pendingOldestHours)}`
          : "queue is empty",
    },
    {
      icon: Clock,
      label: "Avg review time",
      value: sla?.avgReviewHours != null ? `${formatHours(sla.avgReviewHours)}` : "—",
      sub:
        sla?.last7dAvgReviewHours != null
          ? `${formatHours(sla.last7dAvgReviewHours)} this week`
          : "no decisions yet",
    },
    {
      icon: History,
      label: "Decisions · 7 days",
      value: sla?.last7dDecisions ?? "—",
      sub:
        sla?.decisionDelta7d === 0
          ? "same as last week"
          : sla && sla.decisionDelta7d > 0
            ? `▲ +${sla.decisionDelta7d} vs last week`
            : sla && sla.decisionDelta7d < 0
              ? `▼ ${sla.decisionDelta7d} vs last week`
              : "no trend yet",
    },
  ];

  return (
    <>
      {sla && sla.breaches.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-2">
          {sla.breaches.map((key) => {
            const breach = breachLabels[key];
            if (!breach) return null;
            const Icon = breach.icon;
            return (
              <span
                key={key}
                className="inline-flex items-center gap-1.5 rounded-full border border-red-200 bg-red-50 px-3 py-1 text-xs font-semibold text-red-600 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-400"
              >
                <Icon className="size-3.5" />
                {breach.label}
              </span>
            );
          })}
        </div>
      )}
      <div className="mb-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
        {cards.map((c) => (
          <div
            key={c.label}
            className="rounded-xl border border-gray-200 bg-card p-4 dark:border-gray-800"
          >
            <div className="flex items-center gap-2 text-xs font-medium text-gray-500 dark:text-gray-400">
              <c.icon className="size-3.5" /> {c.label}
            </div>
            <p className="mt-1.5 font-display text-2xl font-bold text-foreground">
              {isLoading ? <Loader2 className="size-5 animate-spin text-gray-400" /> : c.value}
            </p>
            <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">{c.sub}</p>
          </div>
        ))}
      </div>
    </>
  );
}

/**
 * Lightweight dependency-free 30-day trend chart (SVG): bars for decisions
 * per day, a line for average review hours. Deliberately hand-rolled so the
 * admin panel adds no chart-library weight to the bundle.
 */
function TrendChart({ trend }: { trend: KycSla["trend30d"] }) {
  const W = 720;
  const H = 220;
  const PAD = { top: 20, right: 16, bottom: 30, left: 40 };
  const iw = W - PAD.left - PAD.right;
  const ih = H - PAD.top - PAD.bottom;

  const maxDecisions = Math.max(1, ...trend.map((d) => d.decisions));
  const maxHours = Math.max(1, ...trend.map((d) => d.avgReviewHours ?? 0));
  const n = trend.length;
  const bw = iw / n;

  const hoursToY = (h: number) => PAD.top + ih - (h / maxHours) * ih;
  const decToY = (dec: number) => PAD.top + ih - (dec / maxDecisions) * ih;

  // Line through the average-review-hours points (skip nulls).
  const linePoints = trend
    .map((d, i) =>
      d.avgReviewHours == null
        ? null
        : `${PAD.left + i * bw + bw / 2},${hoursToY(d.avgReviewHours)}`
    )
    .filter((p): p is string => p !== null)
    .join(" ");

  // X-axis ticks: show every ~5th day so labels don't crowd.
  const ticks = trend.filter((_, i) => i % 5 === 0 || i === n - 1);

  return (
    <div>
      <div className="mb-1 flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400">
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block size-2.5 rounded-sm bg-orange-500" /> Decisions / day
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block size-2.5 rounded-full border-2 border-sky-500" /> Avg review
          hours
        </span>
      </div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        role="img"
        aria-label="KYC decisions and review time over the last 30 days"
      >
        {/* Gridlines */}
        {[0.25, 0.5, 0.75, 1].map((f) => {
          const y = PAD.top + ih - f * ih;
          return (
            <line
              key={f}
              x1={PAD.left}
              y1={y}
              x2={W - PAD.right}
              y2={y}
              stroke="currentColor"
              strokeOpacity="0.08"
              strokeDasharray="3 4"
            />
          );
        })}

        {/* Decision bars */}
        {trend.map((d, i) => (
          <rect
            key={d.date}
            x={PAD.left + i * bw + bw * 0.2}
            y={decToY(d.decisions)}
            width={bw * 0.6}
            height={ih - (decToY(d.decisions) - PAD.top)}
            rx={2}
            fill="#f97316"
            fillOpacity={d.decisions > 0 ? 0.85 : 0.12}
          />
        ))}

        {/* Avg review hours line */}
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

        {/* X-axis labels */}
        {ticks.map((d) => {
          const i = trend.indexOf(d);
          const date = new Date(d.date + "T00:00:00");
          return (
            <text
              key={d.date}
              x={PAD.left + i * bw + bw / 2}
              y={H - 10}
              textAnchor="middle"
              className="fill-current text-[10px] text-gray-400"
            >
              {date.toLocaleDateString(undefined, { month: "short", day: "numeric" })}
            </text>
          );
        })}
      </svg>
    </div>
  );
}

function formatHours(h: number): string {
  if (h < 1) return `${Math.round(h * 60)}m`;
  if (h < 24) return `${Math.round(h)}h`;
  return `${(h / 24).toFixed(1)}d`;
}

function HistoryView() {
  const { data: entries = [], isLoading } = useKycAuditTrail();
  const { data: sla } = useKycSla();

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-15 text-gray-600 dark:text-gray-400">
        <Loader2 className="size-4 animate-spin" /> Loading history…
      </div>
    );
  }

  const trend = sla?.trend30d ?? [];

  if (entries.length === 0) {
    return (
      <div className="flex flex-col items-center px-5 py-15 text-center text-gray-600 dark:text-gray-400">
        <History className="mb-4 size-12" />
        <h3 className="mb-2 font-display text-lg font-bold text-foreground">No decisions yet</h3>
        <p>Every approve/reject will show up here — who decided, when, and why.</p>
      </div>
    );
  }

  return (
    <>
      {/* 30-day review trend — decisions/day (bars) + avg review hours (line). */}
      {trend.length > 0 && (
        <div className="mb-6 rounded-2xl border border-gray-200 bg-card p-5 dark:border-gray-800">
          <h3 className="mb-3 font-display text-sm font-bold text-foreground">
            Review activity · last 30 days
          </h3>
          <TrendChart trend={trend} />
        </div>
      )}

      <ol className="relative space-y-0">
        {entries.map((entry, i) => {
          const approved = entry.action === "kyc.approved";
          const isLast = i === entries.length - 1;
          return (
            <li key={entry.id} className="relative flex gap-4 pb-6 last:pb-0">
              {/* Timeline rail */}
              {!isLast && (
                <span className="absolute left-4 top-9 h-full w-px bg-gray-200 dark:bg-gray-800" />
              )}
              {/* Node */}
              <span
                className={cn(
                  "z-10 flex size-8 shrink-0 items-center justify-center rounded-full border-2 border-card shadow-sm",
                  approved ? "bg-emerald-500/15 text-emerald-500" : "bg-red-500/15 text-red-500"
                )}
              >
                {approved ? <BadgeCheck className="size-4" /> : <X className="size-4" />}
              </span>
              <div className="min-w-0 flex-1 rounded-xl border border-gray-100 bg-gray-50 p-3.5 dark:border-gray-800 dark:bg-gray-800/40">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-semibold text-foreground">
                    {approved ? "Approved" : "Rejected"}{" "}
                    <span className="font-normal text-gray-600 dark:text-gray-400">
                      {entry.userName}
                    </span>
                  </p>
                  <span className="inline-flex items-center gap-1 text-xs text-gray-500">
                    <Clock className="size-3" /> {formatWhen(entry.createdAt)}
                  </span>
                </div>
                <p className="mt-1 text-xs text-gray-600 dark:text-gray-400">
                  by <span className="font-medium text-foreground">{entry.actorName}</span>
                  {entry.note && (
                    <>
                      {" "}
                      · note: <em className="text-gray-500">“{entry.note}”</em>
                    </>
                  )}
                </p>
              </div>
            </li>
          );
        })}
      </ol>
    </>
  );
}

/** Tenant-verification review queue (Phase 12 — two-sided trust). */
function TenantKycQueue() {
  const { data: applications = [], isLoading } = usePendingTenantKycApplications();
  const review = useReviewTenantKycApplication();
  const [notes, setNotes] = useState<Record<number, string>>({});

  const decide = async (userId: number, decision: TenantKycDecision) => {
    try {
      await review.mutateAsync({ userId, decision, note: notes[userId] ?? "" });
      toast.success(
        decision === "approved"
          ? "Tenant approved — the verified-tenant badge is now visible."
          : decision === "needs_review"
            ? "Re-submission requested — the tenant was notified."
            : "Application rejected — the tenant was notified."
      );
      setNotes((n) => ({ ...n, [userId]: "" }));
    } catch (error) {
      toast.error(getApiErrorMessage(error, "Could not update this application."));
    }
  };

  const preview = async (fileUrl: string) => {
    try {
      const blob = await kycService.fetchDocumentFile(fileUrl);
      window.open(URL.createObjectURL(blob), "_blank");
    } catch {
      toast.error("Could not preview the document — check permissions.");
    }
  };

  return isLoading ? (
    <div className="flex items-center gap-2 py-15 text-gray-600 dark:text-gray-400">
      <Loader2 className="size-4 animate-spin" /> Loading tenant applications…
    </div>
  ) : applications.length === 0 ? (
    <div className="flex flex-col items-center px-5 py-15 text-center text-gray-600 dark:text-gray-400">
      <Users className="mb-4 size-12" />
      <h3 className="mb-2 font-display text-lg font-bold text-foreground">
        No pending tenant verifications
      </h3>
      <p>Tenant identity document uploads will show up here.</p>
    </div>
  ) : (
    <div className="flex flex-col gap-4">
      {applications.map((app) => (
        <TenantKycCard
          key={app.id}
          app={app}
          notes={notes}
          setNotes={setNotes}
          onDecide={decide}
          onPreview={preview}
          busy={review.isPending}
        />
      ))}
    </div>
  );
}

/** One pending tenant application with its review actions. */
function TenantKycCard({
  app,
  notes,
  setNotes,
  onDecide,
  onPreview,
  busy,
}: {
  app: TenantKycApplication;
  notes: Record<number, string>;
  setNotes: Dispatch<SetStateAction<Record<number, string>>>;
  onDecide: (userId: number, decision: TenantKycDecision) => void;
  onPreview: (fileUrl: string) => void;
  busy: boolean;
}) {
  // Hoisted so the closure below keeps the non-null narrowing.
  const verification = app.verification;
  return (
    <div className="rounded-2xl border border-gray-200 bg-card p-5 dark:border-gray-800">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 font-display text-sm font-bold text-foreground">
            {app.name || app.username}
            {app.tenantVerified ? (
              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[0.65rem] font-semibold text-emerald-500">
                <BadgeCheck className="size-3" /> Identity Verified
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2 py-0.5 text-[0.65rem] font-semibold text-gray-500 dark:bg-gray-800">
                <ShieldOff className="size-3" /> Unverified
              </span>
            )}
          </div>
          <div className="mt-0.5 text-xs text-gray-600 dark:text-gray-400">
            {app.email} • {app.phone || "no phone"} • tenant
          </div>
        </div>
        <div className="flex gap-2">
          <Button
            size="sm"
            className="bg-emerald-600 text-white hover:bg-emerald-700"
            onClick={() => onDecide(app.id, "approved")}
            disabled={busy}
          >
            {busy ? <Loader2 className="size-3.5 animate-spin" /> : <Check className="size-3.5" />}
            Approve
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="border-amber-300 text-amber-600 hover:bg-amber-50 dark:border-amber-500/40 dark:text-amber-400"
            onClick={() => onDecide(app.id, "needs_review")}
            disabled={busy}
          >
            Needs review
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="border-red-300 text-red-600 hover:bg-red-50 dark:border-red-500/40 dark:text-red-400"
            onClick={() => onDecide(app.id, "rejected")}
            disabled={busy}
          >
            <X className="size-3.5" /> Reject
          </Button>
        </div>
      </div>

      {verification?.autoScreenResult && (
        <div className="mt-3 flex flex-wrap items-center gap-2 rounded-lg border border-gray-100 bg-gray-50 px-3 py-2 text-xs dark:border-gray-800 dark:bg-gray-800/50">
          <span className="font-semibold text-gray-600 dark:text-gray-400">Auto screen</span>
          {verification.autoScreenResult === "recommend_approve" ? (
            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 font-semibold text-emerald-600 dark:text-emerald-400">
              <ShieldCheck className="size-3" /> Approve {verification.autoScreenScore}/100
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/10 px-2 py-0.5 font-semibold text-amber-600 dark:text-amber-400">
              <AlertTriangle className="size-3" /> Review {verification.autoScreenScore ?? "—"}/100
            </span>
          )}
          {verification.autoScreenDetail.reasons.length > 0 && (
            <span
              title={verification.autoScreenDetail.reasons.join(" · ")}
              className="cursor-help text-gray-500 underline decoration-dotted dark:text-gray-400"
            >
              {verification.autoScreenDetail.reasons.length} reason
              {verification.autoScreenDetail.reasons.length > 1 ? "s" : ""} — hover to read
            </span>
          )}
        </div>
      )}

      {verification && (
        <div className="mt-4 flex items-center justify-between gap-2 rounded-lg border border-gray-100 bg-gray-50 px-3 py-2 text-sm dark:border-gray-800 dark:bg-gray-800/50">
          <span className="font-medium text-gray-700 dark:text-gray-300">
            {verification.docTypeDisplay}
          </span>
          <span className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1 text-xs text-gray-500">
              <Clock className="size-3" /> Submitted{" "}
              {new Date(verification.createdAt).toLocaleDateString()}
            </span>
            {verification.fileUrl && (
              <button
                type="button"
                onClick={() => onPreview(verification.fileUrl!)}
                className="inline-flex items-center gap-1 text-xs font-medium text-orange-600 hover:underline dark:text-orange-400"
              >
                Preview <ExternalLink className="size-3" />
              </button>
            )}
          </span>
        </div>
      )}

      <Input
        className="mt-3"
        placeholder="Review note (required for rejection / needs-review, shown to the tenant)"
        value={notes[app.id] ?? ""}
        onChange={(e) => setNotes((n) => ({ ...n, [app.id]: e.target.value }))}
      />
    </div>
  );
}

export default function AdminKycPanel() {
  const { data: applications = [], isLoading } = usePendingKycApplications();
  const review = useReviewKycApplication();
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [view, setView] = useState<"applications" | "history" | "tenant">("applications");

  const decide = async (userId: number, approved: boolean) => {
    try {
      await review.mutateAsync({ userId, approved, note: notes[userId] ?? "" });
      toast.success(approved ? "Application approved — badges applied." : "Application rejected.");
      setNotes((n) => ({ ...n, [userId]: "" }));
    } catch (error) {
      toast.error(getApiErrorMessage(error, "Could not update this application."));
    }
  };

  // The document is private (auth-gated endpoint), so a plain <a href> would
  // 401 in a new tab — fetch it with the JWT as a blob and open an object URL.
  const preview = async (fileUrl: string) => {
    try {
      const blob = await kycService.fetchDocumentFile(fileUrl);
      window.open(URL.createObjectURL(blob), "_blank");
    } catch {
      toast.error("Could not preview the document — check permissions.");
    }
  };

  return (
    <div>
      <div className="mb-5 flex items-center gap-2">
        <ShieldCheck className="size-5 text-emerald-600" />
        <div>
          <h2 className="font-display text-lg font-bold text-foreground">KYC Review Panel</h2>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Approve identity documents to grant the verified badge — every decision is audited.
          </p>
        </div>
      </div>

      {/* Segmented view toggle */}
      <div className="mb-5 flex w-fit gap-1 rounded-xl bg-gray-50 p-1 dark:bg-gray-800">
        <button
          className={cn(
            "inline-flex items-center gap-1.5 rounded-lg px-4 py-1.5 text-sm font-medium transition-colors",
            view === "applications"
              ? "bg-card text-foreground shadow-sm"
              : "text-gray-600 hover:text-foreground dark:text-gray-400"
          )}
          onClick={() => setView("applications")}
        >
          <Users className="size-3.5" /> Applications
          {applications.length > 0 && (
            <span className="rounded-full bg-orange-600 px-1.5 text-[10px] font-bold text-white">
              {applications.length}
            </span>
          )}
        </button>
        <button
          className={cn(
            "inline-flex items-center gap-1.5 rounded-lg px-4 py-1.5 text-sm font-medium transition-colors",
            view === "history"
              ? "bg-card text-foreground shadow-sm"
              : "text-gray-600 hover:text-foreground dark:text-gray-400"
          )}
          onClick={() => setView("history")}
        >
          <History className="size-3.5" /> History
        </button>
        <button
          className={cn(
            "inline-flex items-center gap-1.5 rounded-lg px-4 py-1.5 text-sm font-medium transition-colors",
            view === "tenant"
              ? "bg-card text-foreground shadow-sm"
              : "text-gray-600 hover:text-foreground dark:text-gray-400"
          )}
          onClick={() => setView("tenant")}
        >
          <ShieldCheck className="size-3.5" /> Tenant KYC
        </button>
      </div>

      {view === "applications" && <SlaStats />}

      {view === "history" ? (
        <HistoryView />
      ) : view === "tenant" ? (
        <TenantKycQueue />
      ) : isLoading ? (
        <div className="flex items-center gap-2 py-15 text-gray-600 dark:text-gray-400">
          <Loader2 className="size-4 animate-spin" /> Loading applications…
        </div>
      ) : applications.length === 0 ? (
        <div className="flex flex-col items-center px-5 py-15 text-center text-gray-600 dark:text-gray-400">
          <Users className="mb-4 size-12" />
          <h3 className="mb-2 font-display text-lg font-bold text-foreground">
            No pending applications
          </h3>
          <p>New KYC document uploads will show up here.</p>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {applications.map((app) => (
            <div
              key={app.id}
              className="rounded-2xl border border-gray-200 bg-card p-5 dark:border-gray-800"
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2 font-display text-sm font-bold text-foreground">
                    {app.name || app.username}
                    {app.nidVerified ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[0.65rem] font-semibold text-emerald-500">
                        <BadgeCheck className="size-3" /> Verified
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2 py-0.5 text-[0.65rem] font-semibold text-gray-500 dark:bg-gray-800">
                        <ShieldOff className="size-3" /> Unverified
                      </span>
                    )}
                  </div>
                  <div className="mt-0.5 text-xs text-gray-600 dark:text-gray-400">
                    {app.email} • {app.phone || "no phone"} • {app.role}
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    className="bg-emerald-600 text-white hover:bg-emerald-700"
                    onClick={() => decide(app.id, true)}
                    disabled={review.isPending}
                  >
                    {review.isPending ? (
                      <Loader2 className="size-3.5 animate-spin" />
                    ) : (
                      <Check className="size-3.5" />
                    )}
                    Approve
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="border-red-300 text-red-600 hover:bg-red-50 dark:border-red-500/40 dark:text-red-400"
                    onClick={() => decide(app.id, false)}
                    disabled={review.isPending}
                  >
                    <X className="size-3.5" /> Reject
                  </Button>
                </div>
              </div>

              {/* Documents */}
              <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2">
                {app.documents.map((doc) => (
                  <div
                    key={doc.id}
                    className="flex items-center justify-between gap-2 rounded-lg border border-gray-100 bg-gray-50 px-3 py-2 text-sm dark:border-gray-800 dark:bg-gray-800/50"
                  >
                    <span className="font-medium text-gray-700 dark:text-gray-300">
                      {doc.docTypeDisplay}
                    </span>
                    <span className="flex items-center gap-2">
                      <span
                        className={cn(
                          "inline-flex rounded-full px-2 py-0.5 text-xs font-semibold",
                          docStatusClasses[doc.status]
                        )}
                      >
                        {doc.statusDisplay}
                      </span>
                      <button
                        type="button"
                        onClick={() => preview(doc.fileUrl)}
                        className="inline-flex items-center gap-1 text-xs font-medium text-orange-600 hover:underline dark:text-orange-400"
                      >
                        Preview <ExternalLink className="size-3" />
                      </button>
                    </span>
                  </div>
                ))}
              </div>

              <Input
                className="mt-3"
                placeholder="Review note (shown to the applicant on rejection)"
                value={notes[app.id] ?? ""}
                onChange={(e) => setNotes((n) => ({ ...n, [app.id]: e.target.value }))}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
