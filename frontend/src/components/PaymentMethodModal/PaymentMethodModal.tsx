import { useState } from "react";
import { toast } from "sonner";
import { CreditCard, Loader2, Smartphone } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { Button } from "../ui/button";
import { useInitiatePayment } from "../../hooks/usePayments";
import type { PaymentGateway, PaymentType } from "../../types";
import { cn } from "../../lib/utils";

const paymentTypeLabels: Record<PaymentType, string> = {
  monthly_rent: "Monthly Rent",
  security_deposit: "Security Deposit",
  booking_deposit: "Booking Deposit",
  listing_feature: "Listing Promotion (Featured)",
  listing_premium: "Listing Promotion (Premium)",
};

interface GatewayOption {
  value: PaymentGateway;
  label: string;
  description: string;
  icon: typeof CreditCard;
  activeClasses: string;
}

const gatewayOptions: GatewayOption[] = [
  {
    value: "sslcommerz",
    label: "SSLCommerz",
    description: "Cards, mobile banking",
    icon: CreditCard,
    activeClasses: "border-orange-600 bg-orange-50 dark:bg-orange-950/20",
  },
  {
    value: "bkash",
    label: "bKash",
    description: "Mobile wallet",
    icon: Smartphone,
    activeClasses: "border-pink-600 bg-pink-50 dark:bg-pink-950/20",
  },
];

/** What to pay: which booking, which payment type, how much, and the room's
 * name for display — everything PaymentMethodModal needs to open. */
export interface PaymentRequest {
  bookingId: number;
  paymentType: PaymentType;
  amount: number;
  roomName: string;
}

interface PaymentMethodModalProps {
  request: PaymentRequest | null;
  onClose: () => void;
}

export default function PaymentMethodModal({ request, onClose }: PaymentMethodModalProps) {
  const [gateway, setGateway] = useState<PaymentGateway>("sslcommerz");
  const initiatePayment = useInitiatePayment();

  const handleConfirm = () => {
    if (!request) return;
    initiatePayment.mutate(
      { bookingId: request.bookingId, paymentType: request.paymentType, gateway },
      {
        onSuccess: (result) => {
          if (!result.paymentUrl) {
            toast.error("Payment session started, but the gateway didn't return a checkout link.");
            return;
          }
          // Full page navigation — the gateway checkout page lives outside the SPA.
          window.location.href = result.paymentUrl;
        },
      }
    );
  };

  return (
    <Dialog open={!!request} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-w-md">
        {request && (
          <>
            <DialogHeader>
              <DialogTitle>Pay {paymentTypeLabels[request.paymentType]}</DialogTitle>
              <DialogDescription>{request.roomName}</DialogDescription>
            </DialogHeader>

            <div className="rounded-xl bg-gray-50 p-4 text-center dark:bg-gray-800">
              <div className="text-sm text-gray-600 dark:text-gray-400">Amount Due</div>
              <div className="font-display text-3xl font-bold text-orange-600">
                ৳{request.amount.toLocaleString()}
              </div>
            </div>

            <div className="flex flex-col gap-3">
              <p className="text-sm font-medium text-foreground">Choose a payment method</p>
              <div className="grid grid-cols-2 gap-3">
                {gatewayOptions.map((option) => {
                  const Icon = option.icon;
                  const active = gateway === option.value;
                  return (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => setGateway(option.value)}
                      disabled={initiatePayment.isPending}
                      className={cn(
                        "flex flex-col items-center gap-1.5 rounded-xl border-2 p-4 text-center transition-colors disabled:opacity-50",
                        active ? option.activeClasses : "border-gray-200 dark:border-gray-800"
                      )}
                    >
                      <Icon className="size-5 text-foreground" />
                      <div className="font-display font-bold text-foreground">{option.label}</div>
                      <div className="text-xs text-gray-600 dark:text-gray-400">
                        {option.description}
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={onClose} disabled={initiatePayment.isPending}>
                Cancel
              </Button>
              <Button
                className="bg-orange-600 text-white hover:bg-orange-700"
                onClick={handleConfirm}
                disabled={initiatePayment.isPending}
              >
                {initiatePayment.isPending ? (
                  <>
                    <Loader2 className="size-4 animate-spin" /> Redirecting…
                  </>
                ) : (
                  "Confirm & Pay"
                )}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
