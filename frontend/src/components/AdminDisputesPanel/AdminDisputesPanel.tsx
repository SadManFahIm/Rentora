import { useState } from "react";
import { CheckCircle2, Scale, XCircle } from "lucide-react";
import { toast } from "sonner";
import { useActOnDispute, useAdminDisputes } from "../../hooks/useDisputes";
import { cn } from "../../lib/utils";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";
import type { Dispute, DisputeDecision, DisputeStatus } from "../../types";

const STATUS_TABS: { value: string; label: string }[] = [
  { value: "open", label: "Open" },
  { value: "under_review", label: "Under review" },
  { value: "waiting_for_tenant", label: "Waiting for tenant" },
  { value: "waiting_for_landlord", label: "Waiting for landlord" },
  { value: "escalated", label: "Escalated" },
  { value: "resolved", label: "Resolved" },
  { value: "rejected", label: "Rejected" },
  { value: "all", label: "All" },
];

const statusClasses: Record<string, string> = {
  open: "bg-red-500/10 text-red-500",
  under_review: "bg-amber-500/10 text-amber-500",
  waiting_for_tenant: "bg-blue-500/10 text-blue-500",
  waiting_for_landlord: "bg-blue-500/10 text-blue-500",
  escalated: "bg-purple-500/10 text-purple-500",
  resolved: "bg-emerald-500/10 text-emerald-500",
  rejected: "bg-gray-500/10 text-gray-500",
};

const TRANSITION_OPTIONS: { value: DisputeStatus; label: string }[] = [
  { value: "under_review", label: "Under review" },
  { value: "waiting_for_tenant", label: "Waiting for tenant" },
  { value: "waiting_for_landlord", label: "Waiting for landlord" },
  { value: "escalated", label: "Escalated" },
];

const DECISION_OPTIONS: { value: DisputeDecision; label: string }[] = [
  { value: "release_to_landlord", label: "Release deposit to landlord" },
  { value: "refund_to_tenant", label: "Refund deposit to tenant" },
  { value: "partial", label: "Partial resolution" },
  { value: "none", label: "No deposit decision" },
];

function DisputeAdminCard({
  dispute,
  onAct,
  busy,
}: {
  dispute: Dispute;
  onAct: (payload: {
    action: "transition" | "resolve" | "reject";
    status?: DisputeStatus;
    decision?: DisputeDecision;
    decisionAmount?: number | null;
    resolution?: string;
  }) => void;
  busy: boolean;
}) {
  const [targetStatus, setTargetStatus] = useState<DisputeStatus | "">("");
  const [decision, setDecision] = useState<DisputeDecision | "">("");
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const isOpen = !["resolved", "rejected"].includes(dispute.status);

  return (
    <div className="rounded-2xl border border-gray-200 bg-card p-4 dark:border-gray-800">
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-bold text-foreground">
            #{dispute.id} · {dispute.roomTitle || `Room #${dispute.roomId}`}
          </span>
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
        </div>
        <div className="text-xs text-gray-600 dark:text-gray-400">
          {dispute.openedByUsername} vs {dispute.otherPartyUsername} · booking #{dispute.booking} ·{" "}
          {new Date(dispute.createdAt).toLocaleString()}
        </div>
        {dispute.description && (
          <p className="rounded-lg bg-gray-50 px-3 py-2 text-sm text-gray-600 dark:bg-gray-800/60 dark:text-gray-400">
            {dispute.description}
          </p>
        )}
        {dispute.evidence.length > 0 && (
          <div className="flex flex-col gap-1.5">
            {dispute.evidence.map((e) => (
              <div key={e.id} className="text-xs text-gray-600 dark:text-gray-400">
                <span className="font-semibold">{e.uploadedByUsername}</span> ({e.kindDisplay}):{" "}
                {e.content || (e.file ? "file attached" : "")}
              </div>
            ))}
          </div>
        )}
        {dispute.resolution && (
          <p className="rounded-lg bg-emerald-500/10 px-3 py-2 text-xs text-emerald-700 dark:text-emerald-400">
            <strong>{dispute.decisionDisplay}</strong> — {dispute.resolution}
          </p>
        )}
      </div>

      {isOpen && (
        <div className="mt-3 flex flex-col gap-2 border-t border-gray-100 pt-3 dark:border-gray-800 lg:flex-row lg:items-end">
          <div className="flex min-w-40 flex-1 flex-col gap-1">
            <label className="text-xs font-semibold text-gray-600 dark:text-gray-400">
              Move status
            </label>
            <Select value={targetStatus} onValueChange={(v) => setTargetStatus(v as DisputeStatus)}>
              <SelectTrigger className="h-9">
                <SelectValue placeholder="Select…" />
              </SelectTrigger>
              <SelectContent>
                {TRANSITION_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              size="sm"
              variant="outline"
              className="mt-1 w-fit"
              disabled={busy || !targetStatus}
              onClick={() => onAct({ action: "transition", status: targetStatus as DisputeStatus })}
            >
              Apply
            </Button>
          </div>

          <div className="flex min-w-60 flex-1 flex-col gap-1">
            <label className="text-xs font-semibold text-gray-600 dark:text-gray-400">
              Resolve with decision
            </label>
            <Select value={decision} onValueChange={(v) => setDecision(v as DisputeDecision)}>
              <SelectTrigger className="h-9">
                <SelectValue placeholder="Decision…" />
              </SelectTrigger>
              <SelectContent>
                {DECISION_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <div className="flex gap-1.5">
              <Input
                placeholder="Amount (৳)"
                value={amount}
                onChange={(e) => setAmount(e.target.value.replace(/[^\d.]/g, ""))}
                className="h-9 w-28 text-xs"
                aria-label={`Resolution amount for dispute ${dispute.id}`}
              />
              <Input
                placeholder="Resolution note…"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                className="h-9 flex-1 text-xs"
                aria-label={`Resolution note for dispute ${dispute.id}`}
              />
            </div>
            <Button
              size="sm"
              className="mt-1 w-fit bg-emerald-600 text-white hover:bg-emerald-700"
              disabled={busy || !decision}
              onClick={() =>
                onAct({
                  action: "resolve",
                  decision: (decision || "none") as DisputeDecision,
                  decisionAmount: amount ? Number(amount) : null,
                  resolution: note,
                })
              }
            >
              <CheckCircle2 className="size-3.5" /> Resolve
            </Button>
          </div>

          <Button
            size="sm"
            variant="outline"
            className="shrink-0"
            disabled={busy}
            onClick={() => onAct({ action: "reject", resolution: note })}
          >
            <XCircle className="size-3.5 text-red-500" /> Reject
          </Button>
        </div>
      )}
    </div>
  );
}

export default function AdminDisputesPanel() {
  const [statusTab, setStatusTab] = useState("open");
  const { data: disputes = [], isLoading } = useAdminDisputes(statusTab);
  const act = useActOnDispute();

  const onAct = async (id: number, payload: Parameters<typeof act.mutate>[0]["payload"]) => {
    try {
      await act.mutateAsync({ id, payload });
      toast.success(`Dispute #${id} updated.`);
    } catch {
      toast.error("Could not update the dispute.");
    }
  };

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center gap-2">
        <Scale className="size-5 text-orange-600" />
        <div>
          <h2 className="font-display text-lg font-bold text-foreground">Dispute Resolution</h2>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Every booking dispute with its evidence — transitions, decisions and deposit outcomes
            are audited and both parties are notified.
          </p>
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {STATUS_TABS.map((t) => (
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

      {isLoading ? (
        <div className="py-15 text-center text-gray-600 dark:text-gray-400">Loading disputes…</div>
      ) : disputes.length === 0 ? (
        <div className="flex flex-col items-center rounded-2xl border border-dashed border-gray-300 px-5 py-15 text-center text-gray-600 dark:border-gray-700 dark:text-gray-400">
          <Scale className="mb-4 size-12" />
          <h3 className="mb-2 font-display text-lg font-bold text-foreground">No disputes here</h3>
          <p>Nothing matches the current filter.</p>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {disputes.map((d) => (
            <DisputeAdminCard
              key={d.id}
              dispute={d}
              busy={act.isPending && act.variables?.id === d.id}
              onAct={(payload) => onAct(d.id, payload)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
