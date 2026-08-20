import { api } from "./api";
import type { Plan, Subscription, SubscriptionCheckout, SubscriptionMe } from "../types";

// ============================================================
// SUBSCRIPTION SERVICE — plans catalog + self-serve checkout
// ============================================================

interface ApiPlan {
  code: string;
  name: string;
  description: string;
  price: string | number;
  billing_cycle: string;
  features: string[];
  active: boolean;
}

interface ApiSubscription {
  id: number;
  plan: ApiPlan;
  status: string;
  current_period_start: string | null;
  current_period_end: string | null;
  auto_renew: boolean;
  cancel_at_period_end: boolean;
  created_at: string;
}

function mapPlan(api: ApiPlan): Plan {
  return {
    code: api.code,
    name: api.name,
    description: api.description,
    price: Number(api.price),
    billingCycle: api.billing_cycle as Plan["billingCycle"],
    features: api.features,
    active: api.active,
  };
}

function mapSubscription(api: ApiSubscription | null): Subscription | null {
  if (!api) return null;
  return {
    id: api.id,
    plan: mapPlan(api.plan),
    status: api.status as Subscription["status"],
    currentPeriodStart: api.current_period_start,
    currentPeriodEnd: api.current_period_end,
    autoRenew: api.auto_renew,
    cancelAtPeriodEnd: api.cancel_at_period_end,
    createdAt: api.created_at,
  };
}

export const subscriptionService = {
  /** GET /subscriptions/plans/ — the active plan catalog. */
  async getPlans(): Promise<Plan[]> {
    const { data } = await api.get<{ plans: ApiPlan[] }>("/subscriptions/plans/");
    return data.plans.map(mapPlan);
  },

  /** GET /subscriptions/subscription/me/ */
  async getMySubscription(): Promise<SubscriptionMe> {
    const { data } = await api.get<{
      subscription: ApiSubscription | null;
      entitled_features: string[];
      subscriptions_enabled: boolean;
    }>("/subscriptions/subscription/me/");
    return {
      subscription: mapSubscription(data.subscription),
      entitledFeatures: data.entitled_features,
      subscriptionsEnabled: data.subscriptions_enabled,
    };
  },

  /** POST /subscriptions/subscription/me/ — start checkout for a plan.
   * Amount is decided server-side (Plan.price); the gateway URL is returned. */
  async checkout(planCode: string, method: "sslcommerz" | "bkash"): Promise<SubscriptionCheckout> {
    const { data } = await api.post<{
      payment_url?: string;
      bkash_url?: string;
      transaction_id: string;
      subscription_id: number;
    }>("/subscriptions/subscription/me/", { plan_code: planCode, method });
    return {
      paymentUrl: data.payment_url ?? data.bkash_url ?? "",
      transactionId: data.transaction_id,
      subscriptionId: data.subscription_id,
    };
  },

  /** POST /subscriptions/subscription/:id/cancel/ — cancel at period end. */
  async cancel(subscriptionId: number): Promise<Subscription> {
    const { data } = await api.post<ApiSubscription>(
      `/subscriptions/subscription/${subscriptionId}/cancel/?action=cancel`,
      {}
    );
    return mapSubscription(data) as Subscription;
  },

  /** POST /subscriptions/subscription/:id/renew/ — start a renewal checkout. */
  async renew(
    subscriptionId: number,
    method: "sslcommerz" | "bkash"
  ): Promise<SubscriptionCheckout> {
    const { data } = await api.post<{
      payment_url?: string;
      bkash_url?: string;
      transaction_id: string;
      subscription_id: number;
    }>(`/subscriptions/subscription/${subscriptionId}/renew/?action=renew`, { method });
    return {
      paymentUrl: data.payment_url ?? data.bkash_url ?? "",
      transactionId: data.transaction_id,
      subscriptionId: data.subscription_id,
    };
  },
};

export default subscriptionService;
