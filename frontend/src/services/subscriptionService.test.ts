import { describe, expect, it, vi, beforeEach } from "vitest";

vi.mock("./api", () => ({
  api: { get: vi.fn(), post: vi.fn() },
}));

import { api } from "./api";
import { subscriptionService } from "./subscriptionService";

const apiPlan = (overrides: Record<string, unknown> = {}) => ({
  code: "premium",
  name: "Premium",
  description: "Everything",
  price: "499",
  billing_cycle: "monthly",
  features: ["price_prediction_basic"],
  active: true,
  ...overrides,
});

const apiSubscription = (overrides: Record<string, unknown> = {}) => ({
  id: 7,
  plan: apiPlan(),
  status: "active",
  current_period_start: "2025-01-01T00:00:00Z",
  current_period_end: "2025-01-31T00:00:00Z",
  auto_renew: true,
  cancel_at_period_end: false,
  created_at: "2025-01-01T00:00:00Z",
  ...overrides,
});

describe("subscriptionService", () => {
  beforeEach(() => vi.clearAllMocks());

  it("getPlans maps snake_case to camelCase plans", async () => {
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { plans: [apiPlan(), apiPlan({ code: "free", billing_cycle: "yearly" })] },
    });
    const plans = await subscriptionService.getPlans();
    expect(api.get).toHaveBeenCalledWith("/subscriptions/plans/");
    expect(plans[0]).toMatchObject({ code: "premium", price: 499, billingCycle: "monthly" });
    expect(plans[1].billingCycle).toBe("yearly");
  });

  it("getMySubscription returns null subscription and entitled features", async () => {
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: {
        subscription: null,
        entitled_features: ["price_prediction_basic"],
        subscriptions_enabled: true,
      },
    });
    const me = await subscriptionService.getMySubscription();
    expect(me.subscription).toBeNull();
    expect(me.entitledFeatures).toEqual(["price_prediction_basic"]);
    expect(me.subscriptionsEnabled).toBe(true);
  });

  it("checkout posts plan_code and maps the gateway url", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { bkash_url: "https://gw.example/bkash", transaction_id: "tx-1", subscription_id: 7 },
    });
    const r = await subscriptionService.checkout("premium", "bkash");
    expect(api.post).toHaveBeenCalledWith("/subscriptions/subscription/me/", {
      plan_code: "premium",
      method: "bkash",
    });
    expect(r.paymentUrl).toBe("https://gw.example/bkash");
    expect(r.subscriptionId).toBe(7);
  });

  it("cancel posts to the cancel endpoint with action= cancel", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: apiSubscription() });
    const sub = await subscriptionService.cancel(7);
    expect(api.post).toHaveBeenCalledWith(
      "/subscriptions/subscription/7/cancel/?action=cancel",
      {}
    );
    expect(sub.id).toBe(7);
    expect(sub.plan.code).toBe("premium");
  });
});
