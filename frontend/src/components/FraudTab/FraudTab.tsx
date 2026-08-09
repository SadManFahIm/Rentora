import { Loader2, ShieldAlert, ShieldCheck } from "lucide-react";
import { useApp } from "../../context/AppContext";
import { useFraudReports, useReviewFraudReport, useScanRoom } from "../../hooks/useFraud";
import { cn } from "../../lib/utils";
import { Button } from "../ui/button";

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

/**
 * Fraud-alert tab: reports on the landlord's own listings (admin sees all).
 * Extracted from the dashboard page so the report card + review actions are
 * unit-testable on their own.
 */
export default function FraudTab() {
  const { data: reports = [], isLoading } = useFraudReports();
  const scanRoom = useScanRoom();
  const review = useReviewFraudReport();
  const { user } = useApp();
  const isAdmin = user?.role === "admin";

  if (isLoading) {
    return (
      <div className="py-15 text-center text-gray-600 dark:text-gray-400">
        Loading fraud reports…
      </div>
    );
  }

  return (
    <div>
      <div className="mb-5 flex items-center gap-2">
        <ShieldAlert className="size-5 text-orange-600" />
        <div>
          <h2 className="font-display text-lg font-bold text-foreground">Fraud &amp; Safety</h2>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            {isAdmin
              ? "All listings flagged by the fraud detector."
              : "Auto-detected risk signals on your listings."}
          </p>
        </div>
      </div>

      {reports.length === 0 ? (
        <div className="flex flex-col items-center px-5 py-15 text-center text-gray-600 dark:text-gray-400">
          <ShieldCheck className="mb-4 size-12 text-emerald-500" />
          <h3 className="mb-2 font-display text-lg font-bold text-foreground">
            No flagged listings
          </h3>
          <p>Your listings passed the fraud scan. New rooms are checked automatically.</p>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {reports.map((report) => {
            const isScanning = scanRoom.isPending && scanRoom.variables === report.room.id;
            return (
              <div
                key={report.id}
                className="rounded-2xl border border-gray-200 bg-card p-5 dark:border-gray-800"
              >
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div className="flex items-center gap-3">
                    <img
                      src={report.room.img}
                      alt={report.room.name}
                      className="h-16 w-24 shrink-0 rounded-lg object-cover"
                    />
                    <div>
                      <div className="font-display text-sm font-bold text-foreground">
                        {report.room.name}
                      </div>
                      <div className="text-xs text-gray-600 dark:text-gray-400">
                        {report.room.area} • {report.room.type}
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
                      </div>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => scanRoom.mutate(report.room.id)}
                      disabled={isScanning}
                    >
                      {isScanning ? <Loader2 className="size-3.5 animate-spin" /> : "Re-scan"}
                    </Button>
                    {isAdmin && report.status === "open" && (
                      <>
                        <Button
                          size="sm"
                          onClick={() => review.mutate({ reportId: report.id, action: "reviewed" })}
                        >
                          Mark reviewed
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() =>
                            review.mutate({ reportId: report.id, action: "dismissed" })
                          }
                        >
                          Dismiss
                        </Button>
                      </>
                    )}
                  </div>
                </div>

                {report.signals.length > 0 && (
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
