import { useState } from "react";
import { toast } from "sonner";
import {
  BadgeCheck,
  Check,
  CreditCard,
  Crown,
  Loader2,
  Smartphone,
  Sparkles,
  XCircle,
} from "lucide-react";
import { useMySubscription, usePlans, useSubscribe } from "../../hooks/useSubscriptions";
import { Button } from "../ui/button";
import { Skeleton } from "../ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import type { Plan } from "../../types";
import { cn } from "../../lib/utils";

const gateways = [
  { value: "sslcommerz" as const, label: "SSLCommerz", icon: CreditCard },
  { value: "bkash" as const, label: "bKash", icon: Smartphone },
];

const statusLabel: Record<string, string> = {
  active: "Active",
  pending: "Pending payment",
  canceled: "Cancelled",
  expired: "Expired",
  past_due: "Payment overdue",
};

/** Subscription & plan management — what phase-15 premium features unlock. */
export default function SubscriptionPanel() {
  const { data: me } = useMySubscription();
  const { data: plans = [], isLoading: plansLoading } = usePlans();
  const [selected, setSelected] = useState<Plan | null>(null);
  const subscribe = useSubscribe();

  const active = me?.subscription ?? null;
  const busy = subscribe.isPending;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-2">
        <Sparkles className="size-5 text-orange-600" />
        <div>
          <h2 className="font-display text-lg font-bold text-foreground">
            Rentora Premium — subscriptions
          </h2>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            AI pricing, advanced listing insights and more. Paid via SSLCommerz / bKash, billed
            monthly or yearly.
          </p>
        </div>
      </div>

      {active && (
        <div className="flex flex-col gap-2 rounded-2xl border border-orange-500/40 bg-orange-50 p-4 dark:bg-orange-950/20 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <Crown className="size-6 text-orange-600" />
            <div>
              <div className="font-display font-bold text-foreground">
                {active.plan.name}
                <span
                  className={cn(
                    "ml-2 rounded-full px-2 py-0.5 text-[0.65rem] font-bold",
                    active.status === "active"
                      ? "bg-emerald-500/10 text-emerald-600"
                      : "bg-amber-500/10 text-amber-600"
                  )}
                >
                  {statusLabel[active.status] ?? active.status}
                </span>
              </div>
              <div className="text-xs text-gray-600 dark:text-gray-400">
                Renews {active.currentPeriodEnd ?? "—"} · ৳{active.plan.price.toLocaleString()}/
                {active.plan.billingCycle === "yearly" ? "yr" : "mo"}
                {active.autoRenew ? " · auto-renew on" : " · auto-renew off"}
              </div>
            </div>
          </div>
          {active.status === "active" && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => subscribe.mutate({ planCode: active.plan.code, method: "sslcommerz" })}
              disabled={busy}
            >
              <Loader2 className={cn("size-4", busy && "animate-spin")} /> Renew
            </Button>
          )}
        </div>
      )}

      {me && me.entitledFeatures.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {me.entitledFeatures.map((f) => (
            <span
              key={f}
              className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-3 py-1 text-xs font-semibold text-emerald-600"
            >
              <BadgeCheck className="size-3.5" /> {f}
            </span>
          ))}
        </div>
      )}

      {plansLoading ? (
        <div className="flex flex-col gap-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-28 w-full rounded-2xl" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {plans.map((plan) => {
            const isCurrent = active?.plan.code === plan.code && active.status === "active";
            return (
              <div
                key={plan.code}
                className={cn(
                  "flex flex-col gap-3 rounded-2xl border-2 bg-card p-5",
                  isCurrent ? "border-orange-500" : "border-gray-200 dark:border-gray-800"
                )}
              >
                <div className="flex items-center justify-between">
                  <h3 className="font-display text-lg font-bold text-foreground">{plan.name}</h3>
                  {isCurrent && (
                    <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[0.65rem] font-bold text-emerald-600">
                      Current
                    </span>
                  )}
                </div>
                <p className="text-sm text-gray-600 dark:text-gray-400">{plan.description}</p>
                <div className="font-display text-2xl font-bold text-foreground">
                  ৳{plan.price.toLocaleString()}
                  <span className="text-sm font-medium text-gray-500">
                    /{plan.billingCycle === "yearly" ? "year" : "month"}
                  </span>
                </div>
                <ul className="flex flex-col gap-1.5">
                  {plan.features.map((f) => (
                    <li
                      key={f}
                      className="flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-400"
                    >
                      <Check className="size-3.5 text-emerald-500" /> {f}
                    </li>
                  ))}
                </ul>
                <div className="mt-auto">
                  <Button
                    className="w-full bg-orange-600 text-white hover:bg-orange-700"
                    disabled={isCurrent || busy}
                    onClick={() => setSelected(plan)}
                  >
                    {isCurrent ? "Subscribed" : `Subscribe · ৳${plan.price.toLocaleString()}`}
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <Dialog open={!!selected} onOpenChange={(next) => !next && setSelected(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Subscribe to {selected?.name}</DialogTitle>
            <DialogDescription>
              You'll be redirected to the payment gateway to complete checkout. Your plan activates
              as soon as the payment is confirmed.
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-2">
            {gateways.map((g) => {
              const Icon = g.icon;
              return (
                <Button
                  key={g.value}
                  variant="outline"
                  className="flex items-center justify-center gap-2"
                  disabled={busy}
                  onClick={() =>
                    subscribe.mutate(
                      { planCode: selected?.code ?? "", method: g.value },
                      {
                        onSuccess: (result) => {
                          setSelected(null);
                          if (!result.paymentUrl) {
                            toast.error("Gateway didn't return a redirect link.");
                            return;
                          }
                          window.location.href = result.paymentUrl;
                        },
                      }
                    )
                  }
                >
                  {busy ? <Loader2 className="size-4 animate-spin" /> : <Icon className="size-4" />}
                  Pay with {g.label}
                </Button>
              );
            })}
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setSelected(null)} disabled={busy}>
              <XCircle className="size-4" /> Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
