import { describe, expect, it, vi, beforeEach, afterAll } from "vitest";

vi.mock("./api", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

import { api } from "./api";
import { paymentService } from "./paymentService";

const apiPayment = (overrides: Record<string, unknown> = {}) => ({
  id: 5,
  booking: 11,
  user: 3,
  amount: "199.00",
  payment_method: "sslcommerz",
  payment_type: "listing_feature",
  status: "success",
  transaction_id: "tx-123",
  gateway_transaction_id: "gw-abc",
  failure_reason: "",
  created_at: "2025-01-01T00:00:00Z",
  updated_at: "2025-01-01T00:00:00Z",
  ...overrides,
});

describe("paymentService.initiatePayment", () => {
  beforeEach(() => vi.clearAllMocks());

  it("posts to the sslcommerz endpoint by default", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { payment_url: "https://gw.example/pay", transaction_id: "tx-1" },
    });
    const r = await paymentService.initiatePayment(11, "monthly_rent", "sslcommerz");
    expect(api.post).toHaveBeenCalledWith("/payments/initiate/", {
      booking_id: 11,
      payment_type: "monthly_rent",
    });
    expect(r.paymentUrl).toBe("https://gw.example/pay");
    expect(r.transactionId).toBe("tx-1");
  });

  it("posts to the bkash endpoint and falls back to bkash_url", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { bkash_url: "https://gw.example/bkash", transaction_id: "tx-2" },
    });
    const r = await paymentService.initiatePayment(11, "security_deposit", "bkash");
    expect(api.post).toHaveBeenCalledWith("/payments/bkash/initiate/", {
      booking_id: 11,
      payment_type: "security_deposit",
    });
    expect(r.paymentUrl).toBe("https://gw.example/bkash");
  });

  it("returns an empty url when neither gateway url is present", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { transaction_id: "tx-3" },
    });
    const r = await paymentService.initiatePayment(11, "monthly_rent", "sslcommerz");
    expect(r.paymentUrl).toBe("");
  });
});

describe("paymentService history + summary", () => {
  beforeEach(() => vi.clearAllMocks());

  it("getPaymentHistory maps results and forwards filters", async () => {
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { count: 1, next: null, previous: null, results: [apiPayment()] },
    });
    const payments = await paymentService.getPaymentHistory({
      status: "success",
      method: "sslcommerz",
      type: "listing_feature",
      dateFrom: "2025-01-01",
      dateTo: "2025-01-31",
    });
    expect(api.get).toHaveBeenCalledWith("/payments/", {
      params: {
        status: "success",
        payment_method: "sslcommerz",
        payment_type: "listing_feature",
        date_from: "2025-01-01",
        date_to: "2025-01-31",
      },
    });
    expect(payments[0]).toMatchObject({
      id: 5,
      bookingId: 11,
      amount: 199,
      method: "sslcommerz",
      type: "listing_feature",
      status: "success",
      transactionId: "tx-123",
    });
  });

  it("getPaymentHistory sends no params when no filters", async () => {
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { count: 0, next: null, previous: null, results: [] },
    });
    await paymentService.getPaymentHistory();
    expect(api.get).toHaveBeenCalledWith("/payments/", { params: {} });
  });

  it("getPaymentSummary maps totals to numbers", async () => {
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: {
        total_paid: "5000",
        total_pending: "1000",
        total_refunded: "200",
        count_paid: 3,
        count_pending: 1,
        count_refunded: 1,
      },
    });
    const s = await paymentService.getPaymentSummary();
    expect(api.get).toHaveBeenCalledWith("/payments/summary/");
    expect(s).toEqual({
      totalPaid: 5000,
      totalPending: 1000,
      totalRefunded: 200,
      countPaid: 3,
      countPending: 1,
      countRefunded: 1,
    });
  });

  it("getPaymentDetail fetches and maps a single payment", async () => {
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: apiPayment(),
    });
    const p = await paymentService.getPaymentDetail(5);
    expect(api.get).toHaveBeenCalledWith("/payments/5/");
    expect(p.id).toBe(5);
  });

  it("getPaymentByTransactionId finds the payment or returns null", async () => {
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: {
        count: 2,
        next: null,
        previous: null,
        results: [
          apiPayment({ transaction_id: "tx-other" }),
          apiPayment({ transaction_id: "tx-123" }),
        ],
      },
    });
    const found = await paymentService.getPaymentByTransactionId("tx-123");
    expect(found?.id).toBe(5);
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { count: 1, next: null, previous: null, results: [apiPayment()] },
    });
    await expect(paymentService.getPaymentByTransactionId("missing")).resolves.toBeNull();
  });
});

describe("paymentService downloads", () => {
  const originalWindow = globalThis.window;
  const originalDocument = globalThis.document;

  beforeEach(() => {
    vi.clearAllMocks();
    const click = vi.fn();
    const link = { href: "", download: "", click, remove: vi.fn() };
    (globalThis as Record<string, unknown>).window = {
      URL: { createObjectURL: vi.fn(() => "blob:mock"), revokeObjectURL: vi.fn() },
    };
    (globalThis as Record<string, unknown>).document = {
      createElement: vi.fn(() => link),
      body: { appendChild: vi.fn() },
    };
  });

  afterAll(() => {
    (globalThis as Record<string, unknown>).window = originalWindow;
    (globalThis as Record<string, unknown>).document = originalDocument;
  });

  it("downloadReceipt uses the content-disposition filename", async () => {
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: new Blob(["pdf"]),
      headers: { "content-disposition": 'attachment; filename="receipt-5.pdf"' },
    });
    await paymentService.downloadReceipt(5);
    expect(api.get).toHaveBeenCalledWith("/payments/5/receipt/", { responseType: "blob" });
  });

  it("downloadInvoice falls back when the header is missing", async () => {
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: new Blob(["pdf"]),
      headers: {},
    });
    await paymentService.downloadInvoice(5);
    expect(api.get).toHaveBeenCalledWith("/payments/5/invoice/", { responseType: "blob" });
  });
});

describe("paymentService.getDepositStatus", () => {
  it("maps deposit status fields", async () => {
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: {
        booking_id: 11,
        security_deposit_amount: "6000.00",
        security_deposit_paid: false,
        security_deposit_refunded: false,
        required_before_approval: true,
      },
    });
    const s = await paymentService.getDepositStatus(11);
    expect(api.get).toHaveBeenCalledWith("/bookings/11/deposit-status/");
    expect(s).toEqual({
      bookingId: 11,
      securityDepositAmount: 6000,
      securityDepositPaid: false,
      securityDepositRefunded: false,
      requiredBeforeApproval: true,
    });
  });
});
