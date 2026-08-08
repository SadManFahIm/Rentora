import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Check, Crown, CreditCard, Flame, Loader2, Smartphone } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { Button } from "../ui/button";
import { Skeleton } from "../ui/skeleton";
import { useTierCatalog } from "../../hooks/useRooms";
import { useInitiateTierUpgrade } from "../../hooks/usePayments";
import type { ListingTier, PaymentGateway } from "../../types";
import { cn } from "../../lib/utils";

interface PromoteModalProps {
  room: { id: number; name: string; tier: ListingTier } | null;
  onClose: () => void;
  onPromoted?: (roomId: number) => void;
}

const tierIcons: Record<string, typeof Flame> = {
  free: Flame,
  featured: Flame,
  premium: Crown,
};

const tierCardClasses: Record<string, string> = {
  free: "border-gray-200 dark:border-gray-800",
  featured: "border-orange-500/60",
  premium: "border-amber-500 bg-gradient-to-b from-amber-50 to-card dark:from-amber-950/30",
};

const gatewayOptions: { value: PaymentGateway; label: string; icon: typeof CreditCard }[] = [
  { value: "sslcommerz", label: "SSLCommerz", icon: CreditCard },
  { value: "bkash", label: "bKash", icon: Smartphone },
];

/** Promotion (paid tier upgrade) modal: pick a tier, pick a gateway, pay. */
export default function PromoteModal({ room, onClose, onPromoted }: PromoteModalProps) {
  const { data: catalog, isLoading } = useTierCatalog();
  const [tier, setTier] = useState<ListingTier | null>(
    room?.tier === "free" ? null : (room?.tier ?? null)
  );
  const [gateway, setGateway] = useState<PaymentGateway>("sslcommerz");
  const upgrade = useInitiateTierUpgrade();

  // Keep selection in sync when the modal opens for a different room.
  useEffect(() => {
    if (room) setTier(room.tier === "free" ? null : room.tier);
  }, [room]);

  const activeTier = catalog?.tiers.find((t) => t.tier === tier) ?? null;

  const handleConfirm = () => {
    if (!room || !tier || tier === "free") return;
    upgrade.mutate(
      { roomId: room.id, tier, gateway },
      {
        onSuccess: (result) => {
          onPromoted?.(room.id);
          if (!result.paymentUrl) {
            toast.error("Payment session started, but the gateway didn't return a checkout link.");
            return;
          }
          window.location.href = result.paymentUrl;
        },
      }
    );
  };

  return (
    <Dialog open={!!room} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-w-lg">
        {room && (
          <>
            <DialogHeader>
              <DialogTitle>Promote your listing</DialogTitle>
              <DialogDescription>
                Boost <span className="font-semibold text-foreground">{room.name}</span> to more
                tenants. Higher tiers rank higher in search.
              </DialogDescription>
            </DialogHeader>

            {isLoading ? (
              <div className="flex flex-col gap-3">
                {[0, 1, 2].map((i) => (
                  <Skeleton key={i} className="h-24 w-full rounded-xl" />
                ))}
              </div>
            ) : (
              <div className="flex flex-col gap-3">
                {catalog?.tiers.map((t) => {
                  const Icon = tierIcons[t.tier] ?? Flame;
                  const selected = tier === t.tier;
                  const isCurrent = room.tier === t.tier;
                  const isFree = t.tier === "free";
                  const disabled = isFree || (isCurrent && !isFree);
                  return (
                    <button
                      key={t.tier}
                      type="button"
                      disabled={disabled}
                      onClick={() => setTier(t.tier)}
                      className={cn(
                        "flex items-center gap-3 rounded-xl border-2 p-4 text-left transition-all",
                        tierCardClasses[t.tier] ?? "border-gray-200 dark:border-gray-800",
                        selected && "ring-2 ring-orange-500",
                        disabled && "cursor-not-allowed opacity-50"
                      )}
                    >
                      <span
                        className={cn(
                          "flex size-10 shrink-0 items-center justify-center rounded-full",
                          t.tier === "premium"
                            ? "bg-amber-500/15 text-amber-600"
                            : t.tier === "featured"
                              ? "bg-orange-500/15 text-orange-600"
                              : "bg-gray-200 text-gray-500 dark:bg-gray-700"
                        )}
                      >
                        <Icon className="size-5" />
                      </span>
                      <div className="flex-1">
                        <div className="flex items-center gap-2 font-display font-bold text-foreground">
                          {t.label}
                          {isCurrent && (
                            <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[0.65rem] font-bold text-emerald-600">
                              Active
                            </span>
                          )}
                        </div>
                        <ul className="mt-1 flex flex-col gap-0.5">
                          {t.benefits.map((b) => (
                            <li
                              key={b}
                              className="flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-400"
                            >
                              <Check className="size-3 text-emerald-500" /> {b}
                            </li>
                          ))}
                        </ul>
                      </div>
                      <div className="text-right">
                        <div className="font-display text-lg font-bold text-foreground">
                          {t.price === 0 ? "Free" : `৳${t.price.toLocaleString()}`}
                        </div>
                        {t.price > 0 && (
                          <div className="text-xs text-gray-500">/{catalog?.durationDays} days</div>
                        )}
                      </div>
                    </button>
                  );
                })}
              </div>
            )}

            {activeTier && activeTier.tier !== "free" && (
              <div className="flex flex-col gap-2">
                <p className="text-sm font-medium text-foreground">Pay with</p>
                <div className="grid grid-cols-2 gap-3">
                  {gatewayOptions.map((option) => {
                    const Icon = option.icon;
                    const active = gateway === option.value;
                    return (
                      <button
                        key={option.value}
                        type="button"
                        onClick={() => setGateway(option.value)}
                        disabled={upgrade.isPending}
                        className={cn(
                          "flex items-center justify-center gap-2 rounded-xl border-2 p-3 text-sm font-semibold transition-colors disabled:opacity-50",
                          active
                            ? "border-orange-600 bg-orange-50 text-foreground dark:bg-orange-950/20"
                            : "border-gray-200 text-gray-600 dark:border-gray-800 dark:text-gray-400"
                        )}
                      >
                        <Icon className="size-4" /> {option.label}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            <DialogFooter>
              <Button variant="outline" onClick={onClose} disabled={upgrade.isPending}>
                Cancel
              </Button>
              <Button
                className="bg-orange-600 text-white hover:bg-orange-700"
                onClick={handleConfirm}
                disabled={!activeTier || activeTier.tier === "free" || upgrade.isPending}
              >
                {upgrade.isPending ? (
                  <>
                    <Loader2 className="size-4 animate-spin" /> Redirecting…
                  </>
                ) : activeTier && activeTier.tier !== "free" ? (
                  `Pay ৳${activeTier.price.toLocaleString()} & Promote`
                ) : (
                  "Select a tier"
                )}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
