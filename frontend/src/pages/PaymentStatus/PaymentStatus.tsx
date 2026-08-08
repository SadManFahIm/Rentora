import { useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { CheckCircle2, CircleSlash, Loader2, XCircle } from "lucide-react";
import { Button } from "../../components/ui/button";
import { Skeleton } from "../../components/ui/skeleton";
import {
  useDownloadReceipt,
  useInvalidatePayments,
  usePaymentByTransactionId,
} from "../../hooks/usePayments";
import type { PaymentOutcome } from "../../types";
import { cn } from "../../lib/utils";

interface OutcomeConfig {
  icon: typeof CheckCircle2;
  iconBg: string;
  iconColor: string;
  title: string;
  message: string;
}

const outcomeConfig: Record<PaymentOutcome, OutcomeConfig> = {
  success: {
    icon: CheckCircle2,
    iconBg: "bg-emerald-500/10",
    iconColor: "text-emerald-500",
    title: "Payment Successful",
    message: "Your payment has been confirmed. A receipt is ready to download below.",
  },
  fail: {
    icon: XCircle,
    iconBg: "bg-red-500/10",
    iconColor: "text-red-500",
    title: "Payment Failed",
    message:
      "Your payment didn't go through. No charge was made — you can try again from your dashboard.",
  },
  cancel: {
    icon: CircleSlash,
    iconBg: "bg-gray-500/10",
    iconColor: "text-gray-500",
    title: "Payment Cancelled",
    message: "You cancelled the payment before it completed. No charge was made.",
  },
};

/** Read the `status` query param, defaulting unrecognized/missing values to "fail". */
function parseOutcome(raw: string | null): PaymentOutcome {
  if (raw === "success" || raw === "cancel") return raw;
  return "fail";
}

export default function PaymentStatus() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const transactionId = searchParams.get("transaction_id");
  const outcome = parseOutcome(searchParams.get("status"));

  const { data: payment, isLoading } = usePaymentByTransactionId(transactionId);
  const downloadReceipt = useDownloadReceipt();
  const invalidatePayments = useInvalidatePayments();

  // The backend just settled a payment (or booking/deposit state) in this
  // round trip — make sure the dashboard doesn't show stale data when the
  // user navigates back to it.
  useEffect(() => {
    invalidatePayments();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const config = outcomeConfig[outcome];
  const Icon = config.icon;

  return (
    <div className="mx-auto flex min-h-[70vh] max-w-lg flex-col items-center justify-center px-4 py-16 text-center">
      <div
        className={cn("mb-6 flex size-20 items-center justify-center rounded-full", config.iconBg)}
      >
        <Icon className={cn("size-10", config.iconColor)} />
      </div>
      <h1 className="font-display text-2xl font-bold text-foreground">{config.title}</h1>
      <p className="mt-2 text-gray-600 dark:text-gray-400">{config.message}</p>

      {transactionId && (
        <div className="mt-6 w-full rounded-xl border border-gray-200 bg-card p-4 text-left text-sm dark:border-gray-800">
          <div className="flex items-center justify-between py-1">
            <span className="text-gray-600 dark:text-gray-400">Transaction ID</span>
            <span className="font-mono text-xs text-foreground">{transactionId}</span>
          </div>
          {isLoading ? (
            <div className="flex flex-col gap-2 pt-1">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-2/3" />
            </div>
          ) : (
            payment && (
              <>
                <div className="flex items-center justify-between py-1">
                  <span className="text-gray-600 dark:text-gray-400">Amount</span>
                  <span className="font-semibold text-foreground">
                    ৳{payment.amount.toLocaleString()}
                  </span>
                </div>
                <div className="flex items-center justify-between py-1">
                  <span className="text-gray-600 dark:text-gray-400">Method</span>
                  <span className="capitalize text-foreground">{payment.method}</span>
                </div>
              </>
            )
          )}
        </div>
      )}

      <div className="mt-8 flex w-full flex-col gap-3 sm:flex-row">
        {outcome === "success" && payment && (
          <Button
            className="flex-1 bg-orange-600 text-white hover:bg-orange-700"
            onClick={() => downloadReceipt.mutate(payment.id)}
            disabled={downloadReceipt.isPending}
          >
            {downloadReceipt.isPending ? (
              <>
                <Loader2 className="size-4 animate-spin" /> Downloading…
              </>
            ) : (
              "Download Receipt"
            )}
          </Button>
        )}
        {outcome !== "success" && (
          <Button
            className="flex-1 bg-orange-600 text-white hover:bg-orange-700"
            onClick={() =>
              navigate(
                payment?.type === "listing_feature" || payment?.type === "listing_premium"
                  ? "/dashboard?tab=listings"
                  : "/dashboard?tab=bookings"
              )
            }
          >
            Try Again
          </Button>
        )}
        <Button variant="outline" className="flex-1" onClick={() => navigate("/dashboard")}>
          Back to Dashboard
        </Button>
      </div>
    </div>
  );
}
