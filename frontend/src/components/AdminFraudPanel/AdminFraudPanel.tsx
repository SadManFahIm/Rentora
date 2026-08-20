import { useState } from "react";
import {
  ChevronDown,
  Link2,
  Loader2,
  Phone,
  ScrollText,
  ShieldAlert,
  ShieldCheck,
  ShieldX,
  Users2,
} from "lucide-react";
import {
  useFraudAuditLog,
  useFraudRings,
  useFraudReports,
  useFraudSummary,
  useReviewFraudReport,
} from "../../hooks/useFraud";
import { AREAS } from "../../data/mockData";
import { cn } from "../../lib/utils";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";

const severityClasses: Record<string, string> = {
  clean: "bg-emerald-500/10 text-emerald-500",
  low: "bg-yellow-500/10 text-yellow-500",
  medium: "bg-orange-500/10 text-orange-500",
  high: "bg-red-500/10 text-red-500",
};

const statusClasses: Record<string, string> = {
  open: "bg-red-500/10 text-red-500",
  reviewed: "bg-blue-500/10 text-blue-500",
  dismissed: "bg-gray-500/10 text-gray-500",
};

const DETECTORS = [
  "duplicate_listing",
  "duplicate_image",
  "suspicious_price",
  "missing_images",
  "rapid_listing",
  "unverified_owner",
  "description_similarity",
];

function SummaryCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: number | string;
  tone: "red" | "amber" | "green" | "gray";
}) {
  const tones = {
    red: "border-red-200 dark:border-red-900/60",
    amber: "border-amber-200 dark:border-amber-900/60",
    green: "border-emerald-200 dark:border-emerald-900/60",
    gray: "border-gray-200 dark:border-gray-800",
  };
  return (
    <div className={cn("rounded-xl border bg-card p-4 dark:bg-gray-800/40", tones[tone])}>
      <div className="text-xs text-gray-600 dark:text-gray-400">{label}</div>
      <div className="mt-1 font-display text-2xl font-bold text-foreground">{value}</div>
    </div>
  );
}

/**
 * Admin fraud operations panel — summary stats, filterable/sortable report
 * table with expandable detector evidence, review/dismiss actions, and the
 * append-only audit trail. Admin-only (guarded by the dashboard tab logic +
 * server-side permission checks on every endpoint).
 */
export default function AdminFraudPanel() {
  const [status, setStatus] = useState<string>("all");
  const [severity, setSeverity] = useState<string>("all");
  const [area, setArea] = useState<string>("all");
  const [detector, setDetector] = useState<string>("all");
  const [q, setQ] = useState("");
  const [ordering, setOrdering] = useState<string>("-score");
  const [expanded, setExpanded] = useState<number | null>(null);
  const [showAudit, setShowAudit] = useState(false);
  const [showRings, setShowRings] = useState(false);

  const params = {
    ...(status !== "all" ? { status } : {}),
    ...(severity !== "all" ? { severity } : {}),
    ...(area !== "all" ? { area } : {}),
    ...(detector !== "all" ? { detector } : {}),
    ...(q.trim() ? { q: q.trim() } : {}),
    ordering,
  };

  const { data: summary } = useFraudSummary();
  const { data: reports = [], isLoading } = useFraudReports(params);
  const { data: audit = [] } = useFraudAuditLog();
  const { data: rings } = useFraudRings();
  const review = useReviewFraudReport();

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <ShieldAlert className="size-5 text-orange-600" />
          <div>
            <h2 className="font-display text-lg font-bold text-foreground">Fraud Operations</h2>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              Every flagged listing, risk signals, and the audit trail — powered by the existing
              detector engine.
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => setShowRings((v) => !v)}>
            <Users2 className="size-4" /> {showRings ? "Hide" : "Show"} fraud rings
          </Button>
          <Button variant="outline" size="sm" onClick={() => setShowAudit((v) => !v)}>
            <ScrollText className="size-4" /> {showAudit ? "Hide" : "Show"} audit trail
          </Button>
        </div>
      </div>

      {/* Phase 15 — D8: coordinated-account rings (admin review queue). */}
      {showRings && (
        <div className="rounded-xl border border-gray-200 bg-card p-4 dark:border-gray-800">
          <div className="mb-1 flex items-center gap-2">
            <Users2 className="size-4 text-orange-600" />
            <h3 className="font-display text-sm font-bold text-foreground">
              Coordinated-account rings
            </h3>
            {rings && rings.ring_count > 0 && (
              <span className="rounded-full bg-orange-500/10 px-2 py-0.5 text-xs font-semibold text-orange-600 dark:text-orange-400">
                {rings.ring_count} ring{rings.ring_count === 1 ? "" : "s"} · {rings.user_count}{" "}
                accounts
              </span>
            )}
          </div>
          <p className="mb-3 text-xs text-gray-500 dark:text-gray-400">
            Accounts linked by a shared phone number (strong) or a shared audit IP plus same-area
            listings (weak). A ring flags accounts for priority review — it is not proof of guilt,
            and nothing is ever auto-blocked.
          </p>

          {!rings ? (
            <div className="flex items-center gap-2 py-4 text-xs text-gray-500">
              <Loader2 className="size-3.5 animate-spin" /> Detecting rings…
            </div>
          ) : rings.rings.length === 0 ? (
            <div className="flex items-center gap-2 rounded-lg bg-emerald-500/10 px-3 py-3 text-xs font-medium text-emerald-600 dark:text-emerald-400">
              <ShieldCheck className="size-4" /> No coordinated-account rings detected.
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              {rings.rings.map((ring) => (
                <div
                  key={ring.ring_id}
                  className="rounded-xl border border-gray-200 p-3 dark:border-gray-800"
                >
                  <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
                    <span
                      className={cn(
                        "rounded-full px-2.5 py-0.5 font-bold",
                        ring.score >= 70
                          ? "bg-red-500/10 text-red-600 dark:text-red-400"
                          : ring.score >= 50
                            ? "bg-orange-500/10 text-orange-600 dark:text-orange-400"
                            : "bg-yellow-500/10 text-yellow-600 dark:text-yellow-400"
                      )}
                    >
                      Ring #{ring.ring_id} · score {ring.score}/100
                    </span>
                    <span className="text-gray-500 dark:text-gray-400">
                      {ring.member_count} members · {ring.strong_edges} phone link
                      {ring.strong_edges === 1 ? "" : "s"} · {ring.weak_edges} IP+area link
                      {ring.weak_edges === 1 ? "" : "s"}
                    </span>
                  </div>

                  {/* Members */}
                  <div className="flex flex-wrap gap-2">
                    {ring.members.map((member) => (
                      <div
                        key={member.user_id}
                        className="rounded-lg bg-gray-50 px-2.5 py-1.5 text-[11px] dark:bg-gray-800/60"
                      >
                        <div className="font-semibold text-foreground">
                          {member.username}
                          {member.nid_verified && (
                            <span className="ml-1 text-emerald-600 dark:text-emerald-400">
                              ✓ NID
                            </span>
                          )}
                          {member.tenant_verified && (
                            <span className="ml-1 text-emerald-600 dark:text-emerald-400">
                              ✓ tenant
                            </span>
                          )}
                        </div>
                        <div className="text-gray-500 dark:text-gray-400">
                          {member.role} · {member.listings_count} listing
                          {member.listings_count === 1 ? "" : "s"}
                          {ring.member_scores[String(member.user_id)] != null && (
                            <span className="ml-1 font-semibold text-orange-600 dark:text-orange-400">
                              · {(ring.member_scores[String(member.user_id)] / 100).toFixed(0)}
                              /10
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* Evidence */}
                  <ul className="mt-2 space-y-0.5">
                    {ring.edges.map((edge) => (
                      <li
                        key={`${edge.users[0]}-${edge.users[1]}`}
                        className="flex items-center gap-1.5 text-[11px] text-gray-500 dark:text-gray-400"
                      >
                        {edge.strength === "strong" ? (
                          <Phone className="size-3 shrink-0 text-red-400" />
                        ) : (
                          <Link2 className="size-3 shrink-0 text-amber-500" />
                        )}
                        <span className="font-semibold text-gray-600 dark:text-gray-300">
                          #{edge.users[0]} ↔ #{edge.users[1]}
                        </span>
                        {edge.evidence}
                      </li>
                    ))}
                  </ul>

                  {/* Flagged rooms owned by ring members */}
                  {ring.flagged_rooms.length > 0 && (
                    <div className="mt-2 flex flex-wrap items-center gap-1.5">
                      <span className="text-[11px] text-gray-500 dark:text-gray-400">
                        Flagged listings:
                      </span>
                      {ring.flagged_rooms.map((room) => (
                        <a
                          key={room.room_id}
                          href={`/rooms/${room.room_id}`}
                          target="_blank"
                          rel="noreferrer"
                          className={cn(
                            "rounded-full border px-2 py-0.5 text-[11px] font-semibold",
                            room.severity === "high"
                              ? "border-red-300 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-300"
                              : "border-orange-300 bg-orange-50 text-orange-700 dark:border-orange-800 dark:bg-orange-950/40 dark:text-orange-300"
                          )}
                        >
                          {room.title || `#${room.room_id}`} · {room.area} · {room.severity}
                        </a>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
          {rings && (
            <p className="mt-3 text-[10px] text-gray-400 dark:text-gray-500">{rings.note}</p>
          )}
        </div>
      )}

      {/* Summary stats */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-8">
        <SummaryCard label="Total reports" value={summary?.total ?? "—"} tone="gray" />
        <SummaryCard label="Flagged" value={summary?.flagged ?? "—"} tone="red" />
        <SummaryCard label="High risk" value={summary?.high_risk ?? "—"} tone="red" />
        <SummaryCard label="Medium risk" value={summary?.medium_risk ?? "—"} tone="amber" />
        <SummaryCard label="Low risk" value={summary?.low_risk ?? "—"} tone="amber" />
        <SummaryCard label="Pending review" value={summary?.open ?? "—"} tone="red" />
        <SummaryCard label="Reviewed" value={summary?.reviewed ?? "—"} tone="green" />
        <SummaryCard label="Dismissed" value={summary?.dismissed ?? "—"} tone="gray" />
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-52 flex-1">
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-600 dark:text-gray-400">
            Search
          </label>
          <Input
            placeholder="Listing title or owner…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        <div className="min-w-36">
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-600 dark:text-gray-400">
            Risk
          </label>
          <Select value={severity} onValueChange={setSeverity}>
            <SelectTrigger className="h-9">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All risk levels</SelectItem>
              <SelectItem value="high">High</SelectItem>
              <SelectItem value="medium">Medium</SelectItem>
              <SelectItem value="low">Low</SelectItem>
              <SelectItem value="clean">Clean</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="min-w-36">
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-600 dark:text-gray-400">
            Status
          </label>
          <Select value={status} onValueChange={setStatus}>
            <SelectTrigger className="h-9">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All statuses</SelectItem>
              <SelectItem value="open">Pending review</SelectItem>
              <SelectItem value="reviewed">Reviewed</SelectItem>
              <SelectItem value="dismissed">Dismissed</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="min-w-36">
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-600 dark:text-gray-400">
            Area
          </label>
          <Select value={area} onValueChange={setArea}>
            <SelectTrigger className="h-9">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All areas</SelectItem>
              {AREAS.filter((a) => a !== "All").map((a) => (
                <SelectItem key={a} value={a}>
                  {a}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="min-w-40">
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-600 dark:text-gray-400">
            Detector
          </label>
          <Select value={detector} onValueChange={setDetector}>
            <SelectTrigger className="h-9">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All detectors</SelectItem>
              {DETECTORS.map((d) => (
                <SelectItem key={d} value={d}>
                  {d.replace(/_/g, " ")}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="min-w-36">
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-600 dark:text-gray-400">
            Sort
          </label>
          <Select value={ordering} onValueChange={setOrdering}>
            <SelectTrigger className="h-9">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="-score">Risk score ↓</SelectItem>
              <SelectItem value="score">Risk score ↑</SelectItem>
              <SelectItem value="-created_at">Newest first</SelectItem>
              <SelectItem value="created_at">Oldest first</SelectItem>
              <SelectItem value="-price">Price ↓</SelectItem>
              <SelectItem value="price">Price ↑</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Audit trail */}
      {showAudit && (
        <div className="rounded-xl border border-gray-200 bg-card p-4 dark:border-gray-800">
          <h3 className="mb-3 font-display text-sm font-bold text-foreground">
            Audit trail (append-only)
          </h3>
          {audit.length === 0 ? (
            <p className="text-sm text-gray-500 dark:text-gray-400">
              No fraud review actions recorded yet.
            </p>
          ) : (
            <ul className="flex max-h-60 flex-col gap-2 overflow-y-auto">
              {audit.map((entry) => (
                <li key={entry.id} className="flex items-center gap-2 text-sm">
                  <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-semibold text-gray-700 dark:bg-gray-800 dark:text-gray-300">
                    {entry.action.replace("fraud.report.", "")}
                  </span>
                  <span className="text-gray-600 dark:text-gray-400">
                    {entry.actor ?? "system"} · room {entry.room_id ?? entry.target_id}
                  </span>
                  <span className="ml-auto text-xs text-gray-500 dark:text-gray-500">
                    {new Date(entry.created_at).toLocaleString()}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Report list */}
      {isLoading ? (
        <div className="py-15 text-center text-gray-600 dark:text-gray-400">Loading reports…</div>
      ) : reports.length === 0 ? (
        <div className="flex flex-col items-center rounded-2xl border border-dashed border-gray-300 px-5 py-15 text-center text-gray-600 dark:border-gray-700 dark:text-gray-400">
          <ShieldCheck className="mb-4 size-12 text-emerald-500" />
          <h3 className="mb-2 font-display text-lg font-bold text-foreground">No reports match</h3>
          <p>Try clearing a filter — or the whole platform is clean right now.</p>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {reports.map((report) => {
            const isOpen = expanded === report.id;
            const isReviewing = review.isPending && review.variables?.reportId === report.id;
            return (
              <div
                key={report.id}
                className="rounded-2xl border border-gray-200 bg-card p-4 dark:border-gray-800"
              >
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div className="flex min-w-0 items-center gap-3">
                    <img
                      src={report.room.img}
                      alt={report.room.name}
                      className="h-14 w-20 shrink-0 rounded-lg object-cover"
                    />
                    <div className="min-w-0">
                      <button
                        type="button"
                        className="block max-w-full truncate text-left font-display text-sm font-bold text-foreground hover:text-orange-600"
                        onClick={() => setExpanded(isOpen ? null : report.id)}
                      >
                        {report.room.name}
                      </button>
                      <div className="text-xs text-gray-600 dark:text-gray-400">
                        {report.room.area} · ৳{report.room.price.toLocaleString()}/mo ·{" "}
                        {report.room.owner || "—"}
                      </div>
                      <div className="mt-1.5 flex flex-wrap gap-1.5">
                        <span
                          className={cn(
                            "inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold",
                            severityClasses[report.severity]
                          )}
                        >
                          {report.severityDisplay} risk · {report.score}/100
                        </span>
                        <span
                          className={cn(
                            "inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold",
                            statusClasses[report.status]
                          )}
                        >
                          {report.statusDisplay}
                        </span>
                        <span className="inline-flex items-center gap-0.5 rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600 dark:bg-gray-800 dark:text-gray-400">
                          {report.signals.length} signal{report.signals.length === 1 ? "" : "s"}
                          <ChevronDown
                            className={cn("size-3 transition-transform", isOpen && "rotate-180")}
                          />
                        </span>
                      </div>
                    </div>
                  </div>
                  {report.status === "open" && (
                    <div className="flex shrink-0 gap-2">
                      <Button
                        size="sm"
                        onClick={() => review.mutate({ reportId: report.id, action: "reviewed" })}
                        disabled={isReviewing}
                      >
                        {isReviewing ? (
                          <Loader2 className="size-3.5 animate-spin" />
                        ) : (
                          <ShieldCheck className="size-3.5" />
                        )}
                        Mark reviewed
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => review.mutate({ reportId: report.id, action: "dismissed" })}
                        disabled={isReviewing}
                      >
                        <ShieldX className="size-3.5" /> Dismiss
                      </Button>
                    </div>
                  )}
                </div>

                {isOpen && report.signals.length > 0 && (
                  <div className="mt-4 flex flex-col gap-2 border-t border-gray-100 pt-4 dark:border-gray-800">
                    {report.signals.map((signal) => (
                      <div key={signal.id} className="flex items-start gap-2 text-sm">
                        <span
                          className={cn(
                            "mt-1 size-2 shrink-0 rounded-full",
                            signal.severity === "high"
                              ? "bg-red-500"
                              : signal.severity === "medium"
                                ? "bg-orange-500"
                                : "bg-yellow-500"
                          )}
                        />
                        <div>
                          <span className="font-semibold text-foreground">
                            {signal.detectorDisplay}:
                          </span>{" "}
                          <span className="text-gray-600 dark:text-gray-400">{signal.message}</span>
                          {signal.detector === "duplicate_image" &&
                            Array.isArray(signal.detail?.matched_listing_ids) &&
                            signal.detail.matched_listing_ids.length > 0 && (
                              <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                                <span className="text-xs text-gray-500 dark:text-gray-400">
                                  Matched listings:
                                </span>
                                {signal.detail.matched_listing_ids.map((id: number) => (
                                  <a
                                    key={id}
                                    href={`/rooms/${id}`}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="rounded-full border border-orange-300 bg-orange-50 px-2 py-0.5 text-xs font-semibold text-orange-700 hover:bg-orange-100 dark:border-orange-800 dark:bg-orange-950/40 dark:text-orange-300"
                                  >
                                    #{id}
                                  </a>
                                ))}
                                {typeof signal.detail.similarity === "number" && (
                                  <span className="text-xs text-gray-500 dark:text-gray-400">
                                    similarity {(signal.detail.similarity * 100).toFixed(0)}%
                                  </span>
                                )}
                              </div>
                            )}
                          {Object.keys(signal.detail ?? {}).length > 0 && (
                            <pre className="mt-1.5 max-h-32 overflow-auto rounded-lg bg-gray-50 p-2 text-xs text-gray-600 dark:bg-gray-900 dark:text-gray-400">
                              {JSON.stringify(signal.detail, null, 2)}
                            </pre>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
