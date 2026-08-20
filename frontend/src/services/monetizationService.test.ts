import { describe, expect, it, vi, beforeEach } from "vitest";

vi.mock("./api", () => ({
  api: { get: vi.fn(), post: vi.fn() },
}));

import { api } from "./api";
import { monetizationService } from "./monetizationService";
import { brokerService } from "./brokerService";

const apiPayout = (overrides: Record<string, unknown> = {}) => ({
  id: 3,
  recipient: 9,
  recipient_name: "Rahim Hossain",
  amount: "500",
  method: "bkash",
  account_details: {},
  status: "pending",
  reference: "",
  reason: "",
  created_at: "2025-01-01T00:00:00Z",
  decided_at: null,
  ...overrides,
});

describe("monetizationService", () => {
  beforeEach(() => vi.clearAllMocks());

  it("getRevenueDashboard maps totals and nested collections", async () => {
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: {
        revenue_by_scope: [{ scope: "broker", gross: "1000", platform: "20" }],
        total_revenue: "1000",
        platform_revenue: "20",
        mrr: "400",
        partner_obligations: "980",
        pending_payouts: { count: 1, total: "500" },
        recent_ledger: [
          {
            id: 1,
            entry_type: "commission",
            scope: "broker",
            user: 9,
            gross_amount: "100",
            platform_amount: "2",
            partner_amount: "98",
            currency: "BDT",
            created_at: "2025-01-01T00:00:00Z",
          },
        ],
        recent_commissions: [],
        recent_payouts: [apiPayout()],
      },
    });
    const dash = await monetizationService.getRevenueDashboard();
    expect(api.get).toHaveBeenCalledWith("/monetization/revenue/dashboard/");
    expect(dash.totalRevenue).toBe(1000);
    expect(dash.mrr).toBe(400);
    expect(dash.recentLedger[0]).toMatchObject({ grossAmount: 100, platformAmount: 2 });
    expect(dash.recentPayouts[0].recipientName).toBe("Rahim Hossain");
  });

  it("decidePayout posts the decision and maps the result", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: apiPayout({ status: "approved", decided_at: "2025-01-02T00:00:00Z" }),
    });
    const payout = await monetizationService.decidePayout(3, "approve");
    expect(api.post).toHaveBeenCalledWith("/monetization/payouts/3/decision/", {
      action: "approve",
      reason: "",
    });
    expect(payout.status).toBe("approved");
  });

  it("markPayoutPaid posts reference", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: apiPayout({ status: "paid" }),
    });
    await monetizationService.markPayoutPaid(3, "ref-99");
    expect(api.post).toHaveBeenCalledWith("/monetization/payouts/3/mark-paid/", {
      reference: "ref-99",
    });
  });
});

describe("brokerService", () => {
  beforeEach(() => vi.clearAllMocks());

  it("register posts profile fields and maps both profile + verification", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: {
        profile: {
          id: 1,
          user: 9,
          user_name: "Rahim Hossain",
          license_number: "REA-1",
          years_experience: 3,
          specialization: "Family",
          areas: ["Dhanmondi"],
          referral_code: "RAHIMABC",
          status: "pending",
          is_verified: false,
          created_at: "2025-01-01T00:00:00Z",
        },
        verification: {
          id: 2,
          profile: 1,
          documents: ["https://docs/license.pdf"],
          notes: "",
          status: "pending",
          auto_screen_score: 88,
          auto_screen_result: "approved",
          auto_screen_detail: {},
          created_at: "2025-01-01T00:00:00Z",
        },
      },
    });
    const result = await brokerService.register({
      licenseNumber: "REA-1",
      yearsExperience: 3,
      specialization: "Family",
      areas: ["Dhanmondi"],
      documents: ["https://docs/license.pdf"],
    });
    expect(api.post).toHaveBeenCalledWith(
      "/brokers/register/",
      expect.objectContaining({ license_number: "REA-1" })
    );
    expect(result.profile.referralCode).toBe("RAHIMABC");
    expect(result.verification.autoScreenScore).toBe(88);
  });

  it("requestPayout maps the returned payout", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: apiPayout() });
    const payout = await brokerService.requestPayout(500, "bkash");
    expect(api.post).toHaveBeenCalledWith(
      "/brokers/payouts/request/",
      expect.objectContaining({ amount: 500, method: "bkash" })
    );
    expect(payout.amount).toBe(500);
  });
});
