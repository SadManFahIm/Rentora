import { useState } from "react";
import { ChevronDown, Loader2, Scale, Send } from "lucide-react";
import { toast } from "sonner";
import { useBookings } from "../../hooks/useBookings";
import { useAddDisputeEvidence, useCreateDispute, useDisputes } from "../../hooks/useDisputes";
import { cn } from "../../lib/utils";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";
import type { Dispute, DisputeCategory } from "../../types";

const statusClasses: Record<string, string> = {
  open: "bg-red-500/10 text-red-500",
  under_review: "bg-amber-500/10 text-amber-500",
  waiting_for_tenant: "bg-blue-500/10 text-blue-500",
  waiting_for_landlord: "bg-blue-500/10 text-blue-500",
  escalated: "bg-purple-500/10 text-purple-500",
  resolved: "bg-emerald-500/10 text-emerald-500",
  rejected: "bg-gray-500/10 text-gray-500",
};

const CATEGORIES: { value: DisputeCategory; label: string }[] = [
  { value: "deposit", label: "Security deposit" },
  { value: "property_condition", label: "Property condition" },
  { value: "booking_cancellation", label: "Booking cancellation" },
  { value: "misrepresentation", label: "Misrepresentation" },
  { value: "payment", label: "Payment" },
  { value: "other", label: "Other" },
];

/** One dispute card: status, the other party, and — when expanded — the
 * evidence timeline with an "add evidence" box. */
function DisputeCard({ dispute }: { dispute: Dispute }) {
  const [open, setOpen] = useState(false);
  const [evidenceText, setEvidenceText] = useState("");
  const addEvidence = useAddDisputeEvidence();
  const closed = dispute.status === "resolved" || dispute.status === "rejected";

  const submitEvidence = async () => {
    const content = evidenceText.trim();
    if (!content) return;
    try {
      await addEvidence.mutateAsync({ id: dispute.id, payload: { kind: "text", content } });
      setEvidenceText("");
      toast.success("Evidence added.");
    } catch {
      toast.error("Could not add evidence right now.");
    }
  };

  return (
    <div className="rounded-2xl border border-gray-200 bg-card p-4 dark:border-gray-800">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="flex max-w-full items-center gap-2 text-left"
          >
            <span className="truncate font-display text-sm font-bold text-foreground hover:text-orange-600">
              {dispute.roomTitle || `Room #${dispute.roomId}`}
            </span>
            <ChevronDown className={cn("size-3.5 shrink-0 text-gray-400", open && "rotate-180")} />
          </button>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <span
              className={cn(
                "inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold",
                statusClasses[dispute.status]
              )}
            >
              {dispute.statusDisplay}
            </span>
            <span className="inline-flex rounded-full bg-orange-500/10 px-2.5 py-0.5 text-xs font-semibold text-orange-600 dark:text-orange-400">
              {dispute.categoryDisplay}
            </span>
            <span className="text-xs text-gray-600 dark:text-gray-400">
              vs {dispute.otherPartyUsername}
            </span>
          </div>
          {dispute.description && (
            <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">{dispute.description}</p>
          )}
          {dispute.status === "resolved" && (
            <p className="mt-2 rounded-lg bg-emerald-500/10 px-3 py-2 text-xs text-emerald-700 dark:text-emerald-400">
              <strong>{dispute.decisionDisplay}</strong>
              {dispute.decisionAmount != null &&
                ` · ৳${Number(dispute.decisionAmount).toLocaleString()}`}
              {dispute.resolution && ` — ${dispute.resolution}`}
            </p>
          )}
          {dispute.status === "rejected" && dispute.resolution && (
            <p className="mt-2 rounded-lg bg-gray-100 px-3 py-2 text-xs text-gray-600 dark:bg-gray-800 dark:text-gray-400">
              {dispute.resolution}
            </p>
          )}
        </div>
      </div>

      {open && (
        <div className="mt-4 border-t border-gray-100 pt-4 dark:border-gray-800">
          <h4 className="mb-2 font-display text-xs font-bold uppercase tracking-wide text-gray-500 dark:text-gray-400">
            Evidence
          </h4>
          {dispute.evidence.length === 0 ? (
            <p className="mb-3 text-sm text-gray-500 dark:text-gray-400">
              No evidence yet — add a statement to help the review.
            </p>
          ) : (
            <div className="mb-3 flex flex-col gap-2">
              {dispute.evidence.map((e) => (
                <div
                  key={e.id}
                  className="rounded-lg bg-gray-50 px-3 py-2 text-sm dark:bg-gray-800/60"
                >
                  <div className="text-xs font-semibold text-gray-500 dark:text-gray-400">
                    {e.uploadedByUsername} · {e.kindDisplay} ·{" "}
                    {new Date(e.createdAt).toLocaleString()}
                  </div>
                  {e.content && (
                    <p className="mt-0.5 text-gray-700 dark:text-gray-300">{e.content}</p>
                  )}
                  {e.file && (
                    <a
                      href={e.file}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-1 inline-block text-xs text-orange-600 underline"
                    >
                      View file
                    </a>
                  )}
                </div>
              ))}
            </div>
          )}
          {!closed && (
            <div className="flex gap-2">
              <Input
                placeholder="Add a statement for the reviewer…"
                value={evidenceText}
                onChange={(e) => setEvidenceText(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && submitEvidence()}
              />
              <Button
                size="icon"
                className="shrink-0 rounded-xl bg-orange-600 text-white hover:bg-orange-700"
                onClick={submitEvidence}
                disabled={addEvidence.isPending || !evidenceText.trim()}
                aria-label="Submit evidence"
              >
                {addEvidence.isPending ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <Send className="size-4" />
                )}
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function DisputesTab() {
  const { data: disputes = [], isLoading } = useDisputes();
  const { data: bookings = [] } = useBookings();
  const createDispute = useCreateDispute();

  const [showForm, setShowForm] = useState(false);
  const [bookingId, setBookingId] = useState("");
  const [category, setCategory] = useState<DisputeCategory | "">("");
  const [description, setDescription] = useState("");

  // Only approved bookings can be disputed.
  const approvedBookings = bookings.filter((b) => b.status === "approved");

  const submit = async () => {
    if (!bookingId || !category) return;
    try {
      await createDispute.mutateAsync({
        booking: Number(bookingId),
        category,
        description: description.trim() || undefined,
      });
      toast.success("Dispute opened — the other party has been notified.");
      setShowForm(false);
      setBookingId("");
      setCategory("");
      setDescription("");
    } catch {
      toast.error("Could not open the dispute. Check the booking is approved.");
    }
  };

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <Scale className="size-5 text-orange-600" />
          <div>
            <h2 className="font-display text-lg font-bold text-foreground">Disputes</h2>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              Open a structured dispute on an approved booking; our team reviews the evidence.
            </p>
          </div>
        </div>
        {approvedBookings.length > 0 && (
          <Button
            size="sm"
            className="shrink-0 bg-orange-600 text-white hover:bg-orange-700"
            onClick={() => setShowForm((v) => !v)}
          >
            {showForm ? "Cancel" : "+ Open a dispute"}
          </Button>
        )}
      </div>

      {showForm && (
        <div className="rounded-2xl border border-gray-200 bg-card p-5 dark:border-gray-800">
          <h3 className="mb-3 font-display text-sm font-bold text-foreground">Open a dispute</h3>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-600 dark:text-gray-400">
                Booking
              </label>
              <Select value={bookingId} onValueChange={setBookingId}>
                <SelectTrigger className="h-10">
                  <SelectValue placeholder="Select an approved booking…" />
                </SelectTrigger>
                <SelectContent>
                  {approvedBookings.map((b) => (
                    <SelectItem key={b.bookingId} value={String(b.bookingId)}>
                      {b.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-600 dark:text-gray-400">
                Category
              </label>
              <Select value={category} onValueChange={(v) => setCategory(v as DisputeCategory)}>
                <SelectTrigger className="h-10">
                  <SelectValue placeholder="What is this about?" />
                </SelectTrigger>
                <SelectContent>
                  {CATEGORIES.map((c) => (
                    <SelectItem key={c.value} value={c.value}>
                      {c.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="mt-3">
            <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-600 dark:text-gray-400">
              What happened?
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              maxLength={4000}
              rows={3}
              placeholder="Describe the issue — our team will ask both sides for evidence."
              className="w-full resize-none rounded-lg border border-gray-200 bg-transparent px-3 py-2 text-sm text-foreground placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-orange-500/40 dark:border-gray-700"
            />
          </div>
          <div className="mt-3 flex justify-end">
            <Button
              className="bg-orange-600 text-white hover:bg-orange-700"
              onClick={submit}
              disabled={createDispute.isPending || !bookingId || !category}
            >
              {createDispute.isPending && <Loader2 className="size-4 animate-spin" />}
              Open dispute
            </Button>
          </div>
        </div>
      )}

      {isLoading ? (
        <div className="py-15 text-center text-gray-600 dark:text-gray-400">Loading disputes…</div>
      ) : disputes.length === 0 ? (
        <div className="flex flex-col items-center rounded-2xl border border-dashed border-gray-300 px-5 py-15 text-center text-gray-600 dark:border-gray-700 dark:text-gray-400">
          <Scale className="mb-4 size-12" />
          <h3 className="mb-2 font-display text-lg font-bold text-foreground">No disputes</h3>
          <p>
            If something went wrong with an approved booking, open a dispute and our team will
            review it.
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {disputes.map((d) => (
            <DisputeCard key={d.id} dispute={d} />
          ))}
        </div>
      )}
    </div>
  );
}
