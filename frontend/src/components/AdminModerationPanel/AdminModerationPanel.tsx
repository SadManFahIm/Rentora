import { useState } from "react";
import { CheckCircle2, Loader2, MessageSquareWarning, ShieldCheck, XCircle } from "lucide-react";
import { toast } from "sonner";
import {
  useDecidePhotoModeration,
  useDecideReviewModeration,
  useModerationOverview,
  usePhotoModerationQueue,
  useReviewModerationQueue,
} from "../../hooks/useModeration";
import { cn } from "../../lib/utils";
import { Button } from "../ui/button";
import { Input } from "../ui/input";

const QUEUE_TABS: { value: string; label: string }[] = [
  { value: "attention", label: "Needs review" },
  { value: "approved", label: "Approved" },
  { value: "rejected", label: "Rejected" },
  { value: "all", label: "All" },
];

const statusClasses: Record<string, string> = {
  pending: "bg-amber-500/10 text-amber-500",
  flagged: "bg-red-500/10 text-red-500",
  approved: "bg-emerald-500/10 text-emerald-500",
  rejected: "bg-gray-500/10 text-gray-500",
};

function SummaryCard({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-card p-4 dark:border-gray-800">
      <div className="text-xs text-gray-600 dark:text-gray-400">{label}</div>
      <div className="mt-1 font-display text-2xl font-bold text-foreground">{value}</div>
    </div>
  );
}

/** One queue row: the evidence (preview / image), risk score + signals, and
 * the admin's approve/reject buttons. Every decision is audited server-side
 * and the affected user is notified. */
function DecisionRow({
  id,
  title,
  subtitle,
  preview,
  signals,
  riskScore,
  status,
  statusDisplay,
  createdAt,
  onDecide,
  busy,
}: {
  id: number;
  title: string;
  subtitle: string;
  preview: React.ReactNode;
  signals: { key: string; label: string }[];
  riskScore: number;
  status: string;
  statusDisplay: string;
  createdAt: string;
  onDecide: (action: "approve" | "reject", note: string) => void;
  busy: boolean;
}) {
  const [note, setNote] = useState("");
  const needsReview = status === "pending" || status === "flagged";
  return (
    <div className="rounded-2xl border border-gray-200 bg-card p-4 dark:border-gray-800">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-bold text-foreground">{title}</span>
            <span
              className={cn(
                "inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold",
                statusClasses[status]
              )}
            >
              {statusDisplay}
            </span>
            <span className="inline-flex rounded-full bg-orange-500/10 px-2.5 py-0.5 text-xs font-semibold text-orange-600 dark:text-orange-400">
              risk {riskScore}/100
            </span>
          </div>
          <div className="mt-1 text-xs text-gray-600 dark:text-gray-400">{subtitle}</div>
          {preview}
          {signals.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {signals.map((s) => (
                <span
                  key={s.key}
                  className="inline-flex items-center gap-1 rounded-full bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-700 dark:text-amber-400"
                >
                  <MessageSquareWarning className="size-3" /> {s.label}
                </span>
              ))}
            </div>
          )}
          <p className="mt-1.5 text-xs text-gray-500 dark:text-gray-500">
            {new Date(createdAt).toLocaleString()}
          </p>
        </div>

        {needsReview && (
          <div className="flex shrink-0 flex-col gap-2 lg:w-64">
            <Input
              placeholder="Note for the author (optional)…"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              className="h-9 text-xs"
              aria-label={`Note for item ${id}`}
            />
            <div className="flex gap-1.5">
              <Button
                size="sm"
                variant="outline"
                onClick={() => onDecide("approve", note)}
                disabled={busy}
                className="flex-1"
              >
                {busy ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : (
                  <CheckCircle2 className="size-3.5 text-emerald-500" />
                )}
                Approve
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => onDecide("reject", note)}
                disabled={busy}
                className="flex-1"
              >
                <XCircle className="size-3.5 text-red-500" /> Reject
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function AdminModerationPanel() {
  const [queue, setQueue] = useState<"reviews" | "photos">("reviews");
  const [statusTab, setStatusTab] = useState("attention");

  const { data: overview } = useModerationOverview();
  const { data: reviews = [], isLoading: reviewsLoading } = useReviewModerationQueue(statusTab);
  const { data: photos = [], isLoading: photosLoading } = usePhotoModerationQueue(statusTab);
  const decideReview = useDecideReviewModeration();
  const decidePhoto = useDecidePhotoModeration();

  const decide = async (
    kind: "reviews" | "photos",
    id: number,
    action: "approve" | "reject",
    note: string
  ) => {
    try {
      const mutate = kind === "reviews" ? decideReview : decidePhoto;
      await mutate.mutateAsync({ id, action, note });
      toast.success(`Item #${id} ${action === "approve" ? "approved" : "rejected"}.`);
    } catch {
      toast.error("Could not update this item. Please try again.");
    }
  };

  const isLoading = queue === "reviews" ? reviewsLoading : photosLoading;
  const items = queue === "reviews" ? reviews : photos;

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex items-center gap-2">
        <ShieldCheck className="size-5 text-orange-600" />
        <div>
          <h2 className="font-display text-lg font-bold text-foreground">Content Moderation</h2>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Reviews and photos flagged by the Phase 12.5 detectors — every decision is audited and
            the author is notified.
          </p>
        </div>
      </div>

      {/* Overview counts */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
        <SummaryCard label="Reviews" value={overview?.reviews ?? "—"} />
        <SummaryCard label="Reviews pending" value={overview?.reviewsPending ?? "—"} />
        <SummaryCard label="Photos" value={overview?.photos ?? "—"} />
        <SummaryCard label="Photos pending" value={overview?.photosPending ?? "—"} />
        <SummaryCard label="Photos flagged" value={overview?.photosFlagged ?? "—"} />
        <SummaryCard label="Reviews rejected" value={overview?.reviewsRejected ?? "—"} />
      </div>

      {/* Queue switcher */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex w-fit gap-1 rounded-xl bg-gray-50 p-1 dark:bg-gray-800">
          {(["reviews", "photos"] as const).map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => setQueue(q)}
              className={cn(
                "rounded-lg px-4 py-1.5 text-sm font-medium capitalize transition-colors",
                queue === q
                  ? "bg-card text-foreground shadow-sm"
                  : "text-gray-600 hover:text-foreground dark:text-gray-400"
              )}
            >
              {q}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap gap-1.5">
          {QUEUE_TABS.map((t) => (
            <button
              key={t.value}
              type="button"
              onClick={() => setStatusTab(t.value)}
              className={cn(
                "rounded-full px-3 py-1 text-xs font-semibold transition-colors",
                statusTab === t.value
                  ? "bg-orange-600 text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700"
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* Queue list */}
      {isLoading ? (
        <div className="py-15 text-center text-gray-600 dark:text-gray-400">Loading…</div>
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center rounded-2xl border border-dashed border-gray-300 px-5 py-15 text-center text-gray-600 dark:border-gray-700 dark:text-gray-400">
          <ShieldCheck className="mb-4 size-12 text-emerald-500" />
          <h3 className="mb-2 font-display text-lg font-bold text-foreground">
            This queue is clear
          </h3>
          <p>Nothing matches the current filter.</p>
        </div>
      ) : queue === "reviews" ? (
        <div className="flex flex-col gap-3">
          {reviews.map((r) => (
            <DecisionRow
              key={r.id}
              id={r.id}
              title={`${r.rating}★ review on ${r.roomTitle || `room #${r.roomId}`}`}
              subtitle={`by ${r.authorName || r.authorUsername}`}
              preview={
                <p className="mt-2 rounded-lg bg-gray-50 px-3 py-2 text-sm italic text-gray-600 dark:bg-gray-800/60 dark:text-gray-400">
                  “{r.commentPreview}”
                </p>
              }
              signals={r.signals}
              riskScore={r.riskScore}
              status={r.status}
              statusDisplay={r.statusDisplay}
              createdAt={r.createdAt}
              busy={decideReview.isPending && decideReview.variables?.id === r.id}
              onDecide={(action, note) => decide("reviews", r.id, action, note)}
            />
          ))}
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {photos.map((p) => (
            <DecisionRow
              key={p.id}
              id={p.id}
              title={`${p.targetTypeDisplay} photo${p.roomTitle ? ` for ${p.roomTitle}` : ""}`}
              subtitle={`uploaded by ${p.uploadedByUsername || "—"}`}
              preview={
                <div className="mt-2 flex items-center gap-3">
                  <img
                    src={p.imageUrl}
                    alt=""
                    className="h-16 w-24 rounded-lg object-cover"
                    onError={(e) => {
                      (e.currentTarget as HTMLImageElement).style.display = "none";
                    }}
                  />
                  <div className="text-xs text-gray-500 dark:text-gray-500">
                    {p.phash ? `pHash ${p.phash.slice(0, 8)}…` : "no hash"}
                    {p.roomTitle && (
                      <>
                        <br />
                        {p.signals.find((s) => s.key === "duplicate_image")?.label}
                      </>
                    )}
                  </div>
                </div>
              }
              signals={p.signals}
              riskScore={p.riskScore}
              status={p.status}
              statusDisplay={p.statusDisplay}
              createdAt={p.createdAt}
              busy={decidePhoto.isPending && decidePhoto.variables?.id === p.id}
              onDecide={(action, note) => decide("photos", p.id, action, note)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
