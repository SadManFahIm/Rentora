import { api } from "./api";
import type { Paginated } from "./mappers";
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
// PAYMENT SERVICE — real /payments/ and /bookings/:id/deposit-status/ endpoints
// ============================================================

interface ApiPayment {
  id: number;
  booking: number;
  user: number;
  amount: string | number;
  payment_method: string;
  payment_type: string;
  status: string;
  transaction_id: string;
  gateway_transaction_id: string;
  failure_reason: string;
  created_at: string;
  updated_at: string;
}

interface ApiPaymentSummary {
  total_paid: number;
  total_pending: number;
  total_refunded: number;
  count_paid: number;
  count_pending: number;
  count_refunded: number;
}

interface ApiDepositStatus {
  booking_id: number;
  security_deposit_amount: number | string;
  security_deposit_paid: boolean;
  security_deposit_refunded: boolean;
  required_before_approval: boolean;
}

function mapPayment(apiPayment: ApiPayment): Payment {
  return {
    id: apiPayment.id,
    bookingId: apiPayment.booking,
    amount: Number(apiPayment.amount),
    method: apiPayment.payment_method as Payment["method"],
    type: apiPayment.payment_type as Payment["type"],
    status: apiPayment.status as Payment["status"],
    transactionId: apiPayment.transaction_id,
    gatewayTransactionId: apiPayment.gateway_transaction_id,
    failureReason: apiPayment.failure_reason,
    createdAt: apiPayment.created_at,
    updatedAt: apiPayment.updated_at,
  };
}

/** Translate UI filters into the backend's query parameters. */
function buildFilterParams(filters: PaymentFilters): Record<string, string> {
  const params: Record<string, string> = {};
  if (filters.status) params.status = filters.status;
  if (filters.method) params.payment_method = filters.method;
  if (filters.type) params.payment_type = filters.type;
  if (filters.dateFrom) params.date_from = filters.dateFrom;
  if (filters.dateTo) params.date_to = filters.dateTo;
  return params;
}

/** Pull a filename out of a Content-Disposition header, falling back if absent
 * (the browser may hide the header entirely if the backend doesn't expose it
 * via CORS, so this must never throw). */
function filenameFromDisposition(header: unknown, fallback: string): string {
  if (typeof header !== "string") return fallback;
  const match = /filename="?([^";]+)"?/.exec(header);
  return match ? match[1] : fallback;
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

async function fetchPaymentHistory(filters: PaymentFilters = {}): Promise<Payment[]> {
  const { data } = await api.get<Paginated<ApiPayment>>("/payments/", {
    params: buildFilterParams(filters),
  });
  return data.results.map(mapPayment);
}

export const paymentService = {
  /** POST /payments/initiate/ (SSLCommerz) or /payments/bkash/initiate/ (bKash). */
  async initiatePayment(
    bookingId: number,
    paymentType: PaymentType,
    method: PaymentGateway
  ): Promise<InitiatePaymentResult> {
    const path = method === "bkash" ? "/payments/bkash/initiate/" : "/payments/initiate/";
    const { data } = await api.post<{
      payment_url?: string;
      bkash_url?: string;
      transaction_id: string;
    }>(path, {
      booking_id: bookingId,
      payment_type: paymentType,
    });
    return {
      paymentUrl: data.payment_url ?? data.bkash_url ?? "",
      transactionId: data.transaction_id,
    };
  },

  /** GET /payments/ — the current user's payment history, optionally filtered. */
  getPaymentHistory: fetchPaymentHistory,

  /** GET /payments/summary/ — totals for the payments dashboard cards. */
  async getPaymentSummary(): Promise<PaymentSummary> {
    const { data } = await api.get<ApiPaymentSummary>("/payments/summary/");
    return {
      totalPaid: Number(data.total_paid),
      totalPending: Number(data.total_pending),
      totalRefunded: Number(data.total_refunded),
      countPaid: data.count_paid,
      countPending: data.count_pending,
      countRefunded: data.count_refunded,
    };
  },

  /** GET /payments/:id/ */
  async getPaymentDetail(id: number): Promise<Payment> {
    const { data } = await api.get<ApiPayment>(`/payments/${id}/`);
    return mapPayment(data);
  },

  /** Find a payment by its (gateway-facing) transaction id — used by the
   * payment-status page, which only ever gets a transaction id back from the
   * gateway redirect, not the payment's numeric id. There's no dedicated
   * lookup endpoint, so this scans the (newest-first) history; the payment
   * that was just settled is always at or near the top of the first page. */
  async getPaymentByTransactionId(transactionId: string): Promise<Payment | null> {
    const payments = await fetchPaymentHistory();
    return payments.find((p) => p.transactionId === transactionId) ?? null;
  },

  /** GET /payments/:id/receipt/ — downloads the PDF (only available once the
   * payment has succeeded). */
  async downloadReceipt(id: number): Promise<void> {
    const response = await api.get(`/payments/${id}/receipt/`, { responseType: "blob" });
    const filename = filenameFromDisposition(
      response.headers["content-disposition"],
      `receipt-${id}.pdf`
    );
    downloadBlob(response.data, filename);
  },

  /** GET /payments/:id/invoice/ — downloads the PDF. */
  async downloadInvoice(id: number): Promise<void> {
    const response = await api.get(`/payments/${id}/invoice/`, { responseType: "blob" });
    const filename = filenameFromDisposition(
      response.headers["content-disposition"],
      `invoice-${id}.pdf`
    );
    downloadBlob(response.data, filename);
  },

  /** GET /bookings/:id/deposit-status/ */
  async getDepositStatus(bookingId: number): Promise<DepositStatus> {
    const { data } = await api.get<ApiDepositStatus>(`/bookings/${bookingId}/deposit-status/`);
    return {
      bookingId: data.booking_id,
      securityDepositAmount: Number(data.security_deposit_amount),
      securityDepositPaid: data.security_deposit_paid,
      securityDepositRefunded: data.security_deposit_refunded,
      requiredBeforeApproval: data.required_before_approval,
    };
  },
};

export default paymentService;
