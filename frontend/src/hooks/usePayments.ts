import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { paymentService } from "../services/paymentService";
import { getApiErrorMessage } from "../services/errors";
import { bookingKeys } from "./useBookings";
import type {
  DepositStatus,
  InitiatePaymentResult,
  Payment,
  PaymentFilters,
  PaymentGateway,
  PaymentSummary,
  PaymentType,
} from "../types";

// ============================================================
// PAYMENT QUERY / MUTATION HOOKS
// ============================================================

export const paymentKeys = {
  all: ["payments"] as const,
  history: (filters: PaymentFilters) => [...paymentKeys.all, "history", filters] as const,
  summary: () => [...paymentKeys.all, "summary"] as const,
  detail: (id: number) => [...paymentKeys.all, "detail", id] as const,
  byTransaction: (transactionId: string) =>
    [...paymentKeys.all, "by-transaction", transactionId] as const,
  depositStatus: (bookingId: number) => ["bookings", bookingId, "deposit-status"] as const,
};

/** The current user's payment history, optionally filtered by status/method/type/date range. */
export function usePaymentHistory(filters: PaymentFilters = {}) {
  return useQuery<Payment[]>({
    queryKey: paymentKeys.history(filters),
    queryFn: () => paymentService.getPaymentHistory(filters),
  });
}

/** Totals (paid / pending / refunded) for the payments dashboard cards. */
export function usePaymentSummary() {
  return useQuery<PaymentSummary>({
    queryKey: paymentKeys.summary(),
    queryFn: () => paymentService.getPaymentSummary(),
    staleTime: 30_000,
  });
}

/** A single payment by its numeric id. */
export function usePaymentDetail(id: number | null | undefined) {
  return useQuery<Payment>({
    queryKey: paymentKeys.detail(id ?? -1),
    queryFn: () => paymentService.getPaymentDetail(id as number),
    enabled: id != null,
  });
}

/** Resolves a gateway transaction id (from the post-payment redirect) to the
 * underlying Payment record — used by the payment-status page. */
export function usePaymentByTransactionId(transactionId: string | null) {
  return useQuery<Payment | null>({
    queryKey: paymentKeys.byTransaction(transactionId ?? ""),
    queryFn: () => paymentService.getPaymentByTransactionId(transactionId as string),
    enabled: !!transactionId,
  });
}

/** Security-deposit status for a booking. */
export function useDepositStatus(bookingId: number | null | undefined) {
  return useQuery<DepositStatus>({
    queryKey: paymentKeys.depositStatus(bookingId ?? -1),
    queryFn: () => paymentService.getDepositStatus(bookingId as number),
    enabled: bookingId != null,
  });
}

interface InitiatePaymentVars {
  bookingId: number;
  paymentType: PaymentType;
  gateway: PaymentGateway;
}

/** Start a payment session. On success the caller is handed back the
 * gateway's checkout URL — redirecting there (a full page navigation, since
 * it's an external site) is left to the caller so it can be sequenced with
 * closing the confirmation modal, etc. */
export function useInitiatePayment() {
  return useMutation<InitiatePaymentResult, unknown, InitiatePaymentVars>({
    mutationFn: ({ bookingId, paymentType, gateway }) =>
      paymentService.initiatePayment(bookingId, paymentType, gateway),
    onError: (error) => {
      toast.error(getApiErrorMessage(error, "Could not start payment. Please try again."));
    },
  });
}

/** Download a payment's PDF receipt (only available once it has succeeded). */
export function useDownloadReceipt() {
  return useMutation({
    mutationFn: (id: number) => paymentService.downloadReceipt(id),
    onError: (error) => {
      toast.error(getApiErrorMessage(error, "Could not download the receipt."));
    },
  });
}

/** Download a payment's PDF invoice. */
export function useDownloadInvoice() {
  return useMutation({
    mutationFn: (id: number) => paymentService.downloadInvoice(id),
    onError: (error) => {
      toast.error(getApiErrorMessage(error, "Could not download the invoice."));
    },
  });
}

/** Refresh every payment- and booking-related query — call after returning
 * from a gateway so the dashboard's history/summary/deposit-status/booking
 * list all reflect the new payment. */
export function useInvalidatePayments() {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: paymentKeys.all });
    queryClient.invalidateQueries({ queryKey: bookingKeys.all });
  };
}
