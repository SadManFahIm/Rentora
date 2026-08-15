import { useState } from "react";
import {
  AlertTriangle,
  Ban,
  Flag,
  Loader2,
  MessageSquareWarning,
  ShieldCheck,
  ShieldX,
} from "lucide-react";
import { toast } from "sonner";
import { useActOnReport, useAdminReports } from "../../hooks/useChat";
import { cn } from "../../lib/utils";
import { Button } from "../ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { Input } from "../ui/input";
import type { Report, ReportAdminAction } from "../../types";

const STATUS_TABS: { value: string; label: string }[] = [
  { value: "open", label: "Open" },
  { value: "under_review", label: "Under review" },
  { value: "resolved", label: "Resolved" },
  { value: "dismissed", label: "Dismissed" },
  { value: "escalated", label: "Escalated" },
  { value: "all", label: "All" },
];

const statusClasses: Record<string, string> = {
  open: "bg-red-500/10 text-red-500",
  under_review: "bg-amber-500/10 text-amber-500",
  resolved: "bg-emerald-500/10 text-emerald-500",
  dismissed: "bg-gray-500/10 text-gray-500",
  escalated: "bg-purple-500/10 text-purple-500",
};

/** One report in the queue: who reported whom (optionally anchored to a
 * message), the category + description, and the admin's decision buttons.
 * Every decision is audited server-side (`report.*` audit events) and the
 * reporter is notified of the outcome. */
export default function AdminReportsPanel() {
  const [statusTab, setStatusTab] = useState("open");
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [suspendTarget, setSuspendTarget] = useState<Report | null>(null);

  const { data: allReports = [], isLoading } = useAdminReports("all");
  const act = useActOnReport();

  const reports =
    statusTab === "all" ? allReports : allReports.filter((r) => r.status === statusTab);

  const counts = allReports.reduce<Record<string, number>>((acc, r) => {
    acc[r.status] = (acc[r.status] ?? 0) + 1;
    return acc;
  }, {});

  const actOn = async (report: Report, action: ReportAdminAction, note = "") => {
    try {
      await act.mutateAsync({ reportId: report.id, action, note });
      toast.success(`Report #${report.id} ${action === "dismiss" ? "dismissed" : `${action}ed`}.`);
      if (action === "suspend") setSuspendTarget(null);
    } catch {
      toast.error("Could not update the report. Please try again.");
    }
  };

  const isBusy = (reportId: number) => act.isPending && act.variables?.reportId === reportId;

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex items-center gap-2">
        <Flag className="size-5 text-orange-600" />
        <div>
          <h2 className="font-display text-lg font-bold text-foreground">
            Report Moderation Queue
          </h2>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            User and message reports (Phase 12.4) — every decision is audited and the reporter is
            notified of the outcome.
          </p>
        </div>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {STATUS_TABS.slice(0, 5).map((s) => (
          <div
            key={s.value}
            className="rounded-xl border border-gray-200 bg-card p-4 dark:border-gray-800"
          >
            <div className="text-xs text-gray-600 dark:text-gray-400">{s.label}</div>
            <div className="mt-1 font-display text-2xl font-bold text-foreground">
              {counts[s.value] ?? 0}
            </div>
          </div>
        ))}
      </div>

      {/* Status filter */}
      <div className="flex flex-wrap gap-1.5">
        {STATUS_TABS.map((s) => (
          <button
            key={s.value}
            type="button"
            onClick={() => setStatusTab(s.value)}
            className={cn(
              "rounded-full px-3.5 py-1.5 text-xs font-semibold transition-colors",
              statusTab === s.value
                ? "bg-orange-600 text-white"
                : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700"
            )}
          >
            {s.label}
            {s.value !== "all" && <span className="ml-1 opacity-70">({counts[s.value] ?? 0})</span>}
          </button>
        ))}
      </div>

      {/* Queue */}
      {isLoading ? (
        <div className="py-15 text-center text-gray-600 dark:text-gray-400">Loading reports…</div>
      ) : reports.length === 0 ? (
        <div className="flex flex-col items-center rounded-2xl border border-dashed border-gray-300 px-5 py-15 text-center text-gray-600 dark:border-gray-700 dark:text-gray-400">
          <ShieldCheck className="mb-4 size-12 text-emerald-500" />
          <h3 className="mb-2 font-display text-lg font-bold text-foreground">
            No {statusTab === "all" ? "" : `${statusTab.replace("_", " ")} `}reports
          </h3>
          <p>This queue is clear right now.</p>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {reports.map((report) => {
            const busy = isBusy(report.id);
            const note = notes[report.id] ?? "";
            const isOpen = report.status === "open" || report.status === "under_review";
            return (
              <div
                key={report.id}
                className="rounded-2xl border border-gray-200 bg-card p-4 dark:border-gray-800"
              >
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-bold text-foreground">
                        {report.targetName || report.targetUsername}
                      </span>
                      <span className="text-xs text-gray-500 dark:text-gray-500">reported by</span>
                      <span className="text-sm font-semibold text-gray-600 dark:text-gray-400">
                        {report.reporterName || report.reporterUsername}
                      </span>
                      <span
                        className={cn(
                          "inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold",
                          statusClasses[report.status]
                        )}
                      >
                        {report.statusDisplay}
                      </span>
                      {report.messageId != null && (
                        <span className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600 dark:bg-gray-800 dark:text-gray-400">
                          <MessageSquareWarning className="size-3" /> message #{report.messageId}
                        </span>
                      )}
                    </div>
                    <div className="mt-1.5 flex flex-wrap items-center gap-2">
                      <span className="inline-flex rounded-full bg-orange-500/10 px-2.5 py-0.5 text-xs font-semibold text-orange-600 dark:text-orange-400">
                        {report.categoryDisplay}
                      </span>
                      {report.actionTaken && (
                        <span className="text-xs text-gray-500 dark:text-gray-500">
                          action: {report.actionTakenDisplay}
                        </span>
                      )}
                    </div>
                    {report.description && (
                      <p className="mt-2 rounded-lg bg-gray-50 px-3 py-2 text-sm text-gray-600 dark:bg-gray-800/60 dark:text-gray-400">
                        {report.description}
                      </p>
                    )}
                    <p className="mt-1.5 text-xs text-gray-500 dark:text-gray-500">
                      {new Date(report.createdAt).toLocaleString()}
                      {report.adminNote && (
                        <span className="ml-2 text-amber-600 dark:text-amber-400">
                          note: {report.adminNote}
                        </span>
                      )}
                    </p>
                  </div>

                  {isOpen && (
                    <div className="flex shrink-0 flex-col gap-2 lg:w-64">
                      <Input
                        placeholder="Note for the user (warn/suspend)…"
                        value={note}
                        onChange={(e) =>
                          setNotes((prev) => ({ ...prev, [report.id]: e.target.value }))
                        }
                        className="h-9 text-xs"
                        aria-label={`Note for report ${report.id}`}
                      />
                      <div className="flex flex-wrap gap-1.5">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => actOn(report, "dismiss")}
                          disabled={busy}
                        >
                          {busy ? (
                            <Loader2 className="size-3.5 animate-spin" />
                          ) : (
                            <ShieldX className="size-3.5" />
                          )}
                          Dismiss
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => actOn(report, "warn", note)}
                          disabled={busy}
                        >
                          <AlertTriangle className="size-3.5 text-amber-500" /> Warn
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => actOn(report, "escalate")}
                          disabled={busy}
                        >
                          Escalate
                        </Button>
                        <Button
                          size="sm"
                          className="bg-red-600 text-white hover:bg-red-700"
                          onClick={() => setSuspendTarget(report)}
                          disabled={busy}
                        >
                          <Ban className="size-3.5" /> Suspend
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Suspend confirmation — destructive, deactivates the reported account. */}
      <Dialog open={suspendTarget != null} onOpenChange={(open) => !open && setSuspendTarget(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Ban className="size-4 text-red-500" /> Suspend{" "}
              {suspendTarget ? suspendTarget.targetName || suspendTarget.targetUsername : ""}?
            </DialogTitle>
            <DialogDescription>
              The account is deactivated and the user is notified. Their listings stay but are
              marked unavailable until the suspension is reviewed. This action is audited.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setSuspendTarget(null)}
              disabled={suspendTarget != null && isBusy(suspendTarget.id)}
            >
              Cancel
            </Button>
            <Button
              className="bg-red-600 text-white hover:bg-red-700"
              disabled={suspendTarget == null || isBusy(suspendTarget.id)}
              onClick={() => {
                if (suspendTarget) actOn(suspendTarget, "suspend", notes[suspendTarget.id] ?? "");
              }}
            >
              {suspendTarget != null && isBusy(suspendTarget.id) ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Ban className="size-4" />
              )}
              Suspend account
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
