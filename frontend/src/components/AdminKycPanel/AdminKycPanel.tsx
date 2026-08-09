import { useState } from "react";
import {
  BadgeCheck,
  Check,
  Clock,
  ExternalLink,
  History,
  Loader2,
  ShieldCheck,
  ShieldOff,
  Users,
  X,
} from "lucide-react";
import { toast } from "sonner";
import {
  useKycAuditTrail,
  usePendingKycApplications,
  useReviewKycApplication,
} from "../../hooks/useKyc";
import { kycService } from "../../services/kycService";
import { getApiErrorMessage } from "../../services/errors";
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

function HistoryView() {
  const { data: entries = [], isLoading } = useKycAuditTrail();

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-15 text-gray-600 dark:text-gray-400">
        <Loader2 className="size-4 animate-spin" /> Loading history…
      </div>
    );
  }

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
  );
}

export default function AdminKycPanel() {
  const { data: applications = [], isLoading } = usePendingKycApplications();
  const review = useReviewKycApplication();
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [view, setView] = useState<"applications" | "history">("applications");

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
      </div>

      {view === "history" ? (
        <HistoryView />
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
