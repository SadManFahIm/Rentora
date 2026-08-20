import { useState } from "react";
import { Banknote, Check, Loader2, TrendingUp, Wallet, X } from "lucide-react";
import { toast } from "sonner";
import {
  useDecidePayout,
  useMarkPayoutPaid,
  useRevenueDashboard,
} from "../../hooks/useMonetization";
import { Skeleton } from "../ui/skeleton";
import { Button } from "../ui/button";
import type { Payout } from "../../types";

const PAYOUT_TABS = [
  { value: "pending", label: "Pending" },
  { value: "approved", label: "Approved" },
  { value: "paid", label: "Paid" },
  { value: "rejected", label: "Rejected" },
  { value: "all", label: "All" },
];

const statusClasses: Record<string, string> = {
  pending: "bg-amber-500/10 text-amber-600",
  approved: "bg-blue-500/10 text-blue-600",
  paid: "bg-emerald-500/10 text-emerald-600",
  rejected: "bg-red-500/10 text-red-500",
  canceled: "bg-gray-500/10 text-gray-500",
};

function taka(value: number | null | undefined): string {
  if (value == null) return "—";
  return `৳${value.toLocaleString()}`;
}

/** Admin revenue centre — platform revenue, ledger, commissions, payout queue. */
export default function AdminRevenuePanel() {
  const { data: dash, isLoading } = useRevenueDashboard();
  const decide = useDecidePayout();
  const markPaid = useMarkPayoutPaid();

  const [tab, setTab] = useState("pending");
  const [reference, setReference] = useState<Record<number, string>>({});

  const payouts =
    tab === "all"
      ? (dash?.recentPayouts ?? [])
      : (dash?.recentPayouts ?? []).filter((p) => p.status === tab);

  const decideOn = (p: Payout, action: "approve" | "reject") => {
    decide.mutate({ id: p.id, action });
  };

  if (isLoading || !dash) {
    return (
      <div className="flex flex-col gap-3">
        <Skeleton className="h-32 w-full rounded-2xl" />
        <Skeleton className="h-40 w-full rounded-2xl" />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-2">
        <TrendingUp className="size-5 text-orange-600" />
        <div>
          <h2 className="font-display text-lg font-bold text-foreground">
            Revenue &amp; payout centre
          </h2>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Platform revenue by scope, the commission ledger and the partner payout queue (Phase
            15).
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <div className="rounded-2xl border border-gray-200 bg-card p-5 dark:border-gray-800">
          <div className="text-xs text-gray-500">Gross revenue</div>
          <div className="mt-1 font-display text-2xl font-bold text-foreground">
            {taka(dash.totalRevenue)}
          </div>
        </div>
        <div className="rounded-2xl border border-gray-200 bg-card p-5 dark:border-gray-800">
          <div className="text-xs text-gray-500">Platform revenue</div>
          <div className="mt-1 font-display text-2xl font-bold text-foreground">
            {taka(dash.platformRevenue)}
          </div>
        </div>
        <div className="rounded-2xl border border-gray-200 bg-card p-5 dark:border-gray-800">
          <div className="text-xs text-gray-500">Monthly (MRR)</div>
          <div className="mt-1 font-display text-2xl font-bold text-foreground">
            {taka(dash.mrr)}
          </div>
        </div>
        <div className="rounded-2xl border border-gray-200 bg-card p-5 dark:border-gray-800">
          <div className="text-xs text-gray-500">Pending payouts</div>
          <div className="mt-1 font-display text-2xl font-bold text-foreground">
            {dash.pendingPayouts.count} · {taka(dash.pendingPayouts.total)}
          </div>
        </div>
      </div>

      {dash.revenueByScope.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {dash.revenueByScope.map((row) => (
            <div
              key={row.scope}
              className="rounded-xl border border-gray-200 bg-card px-4 py-2 text-sm dark:border-gray-800"
            >
              <span className="capitalize text-gray-500">{row.scope}</span>
              <span className="ml-2 font-semibold text-foreground">
                {taka(row.platform ?? row.gross)}
              </span>
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-col gap-2">
        <h3 className="flex items-center gap-2 font-display font-bold text-foreground">
          <Wallet className="size-4 text-orange-600" /> Payout requests
        </h3>
        <div className="flex flex-wrap gap-1.5">
          {PAYOUT_TABS.map((t) => (
            <button
              key={t.value}
              type="button"
              onClick={() => setTab(t.value)}
              className={
                tab === t.value
                  ? "rounded-full bg-orange-600 px-3.5 py-1.5 text-xs font-semibold text-white"
                  : "rounded-full bg-gray-100 px-3.5 py-1.5 text-xs font-semibold text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400"
              }
            >
              {t.label}
            </button>
          ))}
        </div>

        {payouts.length === 0 ? (
          <p className="rounded-2xl border border-dashed border-gray-300 p-6 text-center text-sm text-gray-500 dark:border-gray-700">
            No payout requests in this state.
          </p>
        ) : (
          <div className="overflow-x-auto rounded-2xl border border-gray-200 dark:border-gray-800">
            <table className="w-full min-w-[640px] text-sm">
              <thead className="bg-gray-50 text-left text-xs text-gray-500 dark:bg-gray-800">
                <tr>
                  <th className="px-4 py-2.5">Recipient</th>
                  <th className="px-4 py-2.5">Amount</th>
                  <th className="px-4 py-2.5">Method</th>
                  <th className="px-4 py-2.5">Status</th>
                  <th className="px-4 py-2.5">Requested</th>
                  <th className="px-4 py-2.5">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {payouts.map((p) => (
                  <tr key={p.id}>
                    <td className="px-4 py-2.5 font-medium text-foreground">{p.recipientName}</td>
                    <td className="px-4 py-2.5 font-semibold text-foreground">{taka(p.amount)}</td>
                    <td className="px-4 py-2.5 capitalize text-gray-600 dark:text-gray-400">
                      {p.method}
                    </td>
                    <td className="px-4 py-2.5">
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-semibold capitalize ${
                          statusClasses[p.status] ?? "bg-gray-500/10 text-gray-500"
                        }`}
                      >
                        {p.status}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-gray-500">
                      {new Date(p.createdAt).toLocaleDateString()}
                    </td>
                    <td className="px-4 py-2.5">
                      {p.status === "pending" && (
                        <div className="flex items-center gap-1.5">
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={decide.isPending}
                            onClick={() => decideOn(p, "approve")}
                          >
                            <Check className="size-3.5 text-emerald-600" /> Approve
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={decide.isPending}
                            onClick={() => decideOn(p, "reject")}
                          >
                            <X className="size-3.5 text-red-500" /> Reject
                          </Button>
                        </div>
                      )}
                      {p.status === "approved" && (
                        <div className="flex items-center gap-1.5">
                          <input
                            className="h-8 w-28 rounded-md border border-gray-200 px-2 text-xs dark:border-gray-700 dark:bg-gray-800"
                            placeholder="txn ref"
                            value={reference[p.id] ?? ""}
                            onChange={(e) => setReference({ ...reference, [p.id]: e.target.value })}
                          />
                          <Button
                            size="sm"
                            className="bg-emerald-600 text-white hover:bg-emerald-700"
                            disabled={markPaid.isPending}
                            onClick={() => {
                              if (!reference[p.id]?.trim()) {
                                toast.error("Enter a transaction reference first.");
                                return;
                              }
                              markPaid.mutate({ id: p.id, reference: reference[p.id] });
                            }}
                          >
                            {markPaid.isPending ? (
                              <Loader2 className="size-3.5 animate-spin" />
                            ) : (
                              <Banknote className="size-3.5" />
                            )}{" "}
                            Mark paid
                          </Button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {dash.recentLedger.length > 0 && (
        <div className="flex flex-col gap-2">
          <h3 className="font-display font-bold text-foreground">Recent ledger entries</h3>
          <div className="overflow-x-auto rounded-2xl border border-gray-200 dark:border-gray-800">
            <table className="w-full min-w-[560px] text-sm">
              <thead className="bg-gray-50 text-left text-xs text-gray-500 dark:bg-gray-800">
                <tr>
                  <th className="px-4 py-2.5">Type</th>
                  <th className="px-4 py-2.5">Scope</th>
                  <th className="px-4 py-2.5">Gross</th>
                  <th className="px-4 py-2.5">Platform</th>
                  <th className="px-4 py-2.5">Partner</th>
                  <th className="px-4 py-2.5">Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {dash.recentLedger.map((entry) => (
                  <tr key={entry.id}>
                    <td className="px-4 py-2.5 capitalize text-foreground">
                      {entry.entryType.replace(/_/g, " ")}
                    </td>
                    <td className="px-4 py-2.5 capitalize text-gray-600 dark:text-gray-400">
                      {entry.scope}
                    </td>
                    <td className="px-4 py-2.5">{taka(entry.grossAmount)}</td>
                    <td className="px-4 py-2.5 font-semibold text-foreground">
                      {taka(entry.platformAmount)}
                    </td>
                    <td className="px-4 py-2.5">{taka(entry.partnerAmount)}</td>
                    <td className="px-4 py-2.5 text-gray-500">
                      {new Date(entry.createdAt).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
