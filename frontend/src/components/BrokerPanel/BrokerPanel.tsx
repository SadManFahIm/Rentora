import { useState } from "react";
import { Award, Banknote, Briefcase, CheckCircle2, HandCoins, Loader2, Share2 } from "lucide-react";
import { useBrokerProfile, useRegisterBroker, useRequestPayout } from "../../hooks/useBrokers";
import { useBrokerDashboard } from "../../hooks/useBrokers";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Skeleton } from "../ui/skeleton";
import { cn } from "../../lib/utils";

const statusLabel: Record<string, string> = {
  unverified: "Not yet verified",
  pending: "Verification pending",
  verified: "Verified",
  rejected: "Rejected",
  suspended: "Suspended",
};

/** Broker network panel — apply to become a broker, see commissions, request payouts. */
export default function BrokerPanel() {
  const { data: profile } = useBrokerProfile();
  const { data: dash, isLoading: dashLoading } = useBrokerDashboard();
  const register = useRegisterBroker();
  const requestPayout = useRequestPayout();

  const [form, setForm] = useState({
    licenseNumber: "",
    yearsExperience: 2,
    specialization: "",
    areas: "",
    documents: "",
  });
  const [payoutAmount, setPayoutAmount] = useState("");

  if (dashLoading && !profile) {
    return (
      <div className="flex flex-col gap-3">
        <Skeleton className="h-32 w-full rounded-2xl" />
        <Skeleton className="h-40 w-full rounded-2xl" />
      </div>
    );
  }

  if (!profile && !dash) {
    const submit = () => {
      if (!form.licenseNumber.trim() || !form.specialization.trim()) return;
      register.mutate({
        licenseNumber: form.licenseNumber,
        yearsExperience: form.yearsExperience,
        specialization: form.specialization,
        areas: form.areas
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        documents: form.documents
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
      });
    };

    return (
      <div className="flex flex-col gap-6">
        <div className="flex items-center gap-2">
          <Briefcase className="size-5 text-orange-600" />
          <div>
            <h2 className="font-display text-lg font-bold text-foreground">Become a broker</h2>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              Verified brokers earn a {`2%`} commission on matched bookings. Submit your license for
              screening.
            </p>
          </div>
        </div>
        <div className="grid max-w-lg grid-cols-1 gap-4 rounded-2xl border border-gray-200 bg-card p-5 dark:border-gray-800">
          <label className="flex flex-col gap-1.5 text-sm font-medium text-foreground">
            Real estate license number
            <Input
              value={form.licenseNumber}
              onChange={(e) => setForm({ ...form, licenseNumber: e.target.value })}
              placeholder="e.g. REA-2024-0112"
            />
          </label>
          <label className="flex flex-col gap-1.5 text-sm font-medium text-foreground">
            Years of experience
            <Input
              type="number"
              min={0}
              value={form.yearsExperience}
              onChange={(e) => setForm({ ...form, yearsExperience: Number(e.target.value) })}
            />
          </label>
          <label className="flex flex-col gap-1.5 text-sm font-medium text-foreground">
            Specialization
            <Input
              value={form.specialization}
              onChange={(e) => setForm({ ...form, specialization: e.target.value })}
              placeholder="e.g. Family rentals, student housing"
            />
          </label>
          <label className="flex flex-col gap-1.5 text-sm font-medium text-foreground">
            Areas covered (comma separated)
            <Input
              value={form.areas}
              onChange={(e) => setForm({ ...form, areas: e.target.value })}
              placeholder="Dhanmondi, Uttara, Bashundhara"
            />
          </label>
          <label className="flex flex-col gap-1.5 text-sm font-medium text-foreground">
            Document URLs (comma separated)
            <Input
              value={form.documents}
              onChange={(e) => setForm({ ...form, documents: e.target.value })}
              placeholder="https://…/license.pdf, https://…/nid.jpg"
            />
          </label>
          <Button
            className="bg-orange-600 text-white hover:bg-orange-700"
            disabled={register.isPending || !form.licenseNumber.trim()}
            onClick={submit}
          >
            {register.isPending ? <Loader2 className="size-4 animate-spin" /> : null} Apply now
          </Button>
        </div>
      </div>
    );
  }

  const current = dash ?? {
    profile: profile as NonNullable<typeof profile>,
    availableBalance: 0,
    summary: { pendingCount: 0, pendingTotal: 0, paidTotal: 0 },
    recentCommissions: [],
    shareUrl: "",
  };

  const canPayout = current.availableBalance > 0;
  const submitPayout = () => {
    const amount = Number(payoutAmount);
    if (!amount || amount <= 0) return;
    requestPayout.mutate({ amount, method: "bkash", accountDetails: { method: "bkash" } });
    setPayoutAmount("");
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-2">
        <Briefcase className="size-5 text-orange-600" />
        <div>
          <h2 className="font-display text-lg font-bold text-foreground">Broker dashboard</h2>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Earn commission on every booking you refer. Payouts are reviewed by the platform.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="rounded-2xl border border-gray-200 bg-card p-5 dark:border-gray-800">
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <Banknote className="size-4" /> Available balance
          </div>
          <div className="mt-1 font-display text-2xl font-bold text-foreground">
            ৳{current.availableBalance.toLocaleString()}
          </div>
        </div>
        <div className="rounded-2xl border border-gray-200 bg-card p-5 dark:border-gray-800">
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <HandCoins className="size-4" /> Pending commissions
          </div>
          <div className="mt-1 font-display text-2xl font-bold text-foreground">
            {current.summary.pendingCount} · ৳{current.summary.pendingTotal.toLocaleString()}
          </div>
        </div>
        <div className="rounded-2xl border border-gray-200 bg-card p-5 dark:border-gray-800">
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <CheckCircle2 className="size-4" /> Lifetime paid
          </div>
          <div className="mt-1 font-display text-2xl font-bold text-foreground">
            ৳{current.summary.paidTotal.toLocaleString()}
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-4 rounded-2xl border border-gray-200 bg-card p-5 dark:border-gray-800 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span
              className={cn(
                "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-bold",
                current.profile.isVerified
                  ? "bg-emerald-500/10 text-emerald-600"
                  : "bg-amber-500/10 text-amber-600"
              )}
            >
              <Award className="size-3.5" />
              {statusLabel[current.profile.status] ?? current.profile.status}
            </span>
          </div>
          <div className="mt-2 text-sm text-gray-600 dark:text-gray-400">
            Referral code:{" "}
            <span className="font-mono font-bold text-foreground">
              {current.profile.referralCode}
            </span>
          </div>
          {current.shareUrl && (
            <button
              type="button"
              onClick={() => navigator.clipboard?.writeText(current.shareUrl)}
              className="mt-1 flex items-center gap-1 text-xs font-semibold text-orange-600 hover:underline"
            >
              <Share2 className="size-3.5" /> Copy share link
            </button>
          )}
        </div>
        <div className="flex flex-col gap-2 sm:w-64">
          <Input
            type="number"
            min={0}
            max={current.availableBalance}
            value={payoutAmount}
            onChange={(e) => setPayoutAmount(e.target.value)}
            placeholder={`Max ৳${current.availableBalance.toLocaleString()}`}
            disabled={!canPayout}
          />
          <Button
            className="bg-orange-600 text-white hover:bg-orange-700"
            disabled={!canPayout || !payoutAmount}
            onClick={submitPayout}
          >
            {requestPayout.isPending ? <Loader2 className="size-4 animate-spin" /> : null} Request
            payout
          </Button>
        </div>
      </div>

      {current.recentCommissions.length > 0 && (
        <div className="flex flex-col gap-2">
          <h3 className="font-display font-bold text-foreground">Recent commissions</h3>
          <div className="overflow-x-auto rounded-2xl border border-gray-200 dark:border-gray-800">
            <table className="w-full min-w-[480px] text-sm">
              <thead className="bg-gray-50 text-left text-xs text-gray-500 dark:bg-gray-800">
                <tr>
                  <th className="px-4 py-2.5">Type</th>
                  <th className="px-4 py-2.5">Amount</th>
                  <th className="px-4 py-2.5">Status</th>
                  <th className="px-4 py-2.5">Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {current.recentCommissions.map((c) => (
                  <tr key={c.id}>
                    <td className="px-4 py-2.5 capitalize text-foreground">
                      {c.kind.replace(/_/g, " ")}
                    </td>
                    <td className="px-4 py-2.5 font-semibold text-foreground">
                      ৳{c.amount.toLocaleString()}
                    </td>
                    <td className="px-4 py-2.5">
                      <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-semibold capitalize text-gray-600 dark:bg-gray-800 dark:text-gray-400">
                        {c.status}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-gray-500">
                      {new Date(c.createdAt).toLocaleDateString()}
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
