import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { subscriptionService } from "../services/subscriptionService";
import { getApiErrorMessage } from "../services/errors";
import type { Plan, Subscription, SubscriptionCheckout, SubscriptionMe } from "../types";

// ============================================================
// SUBSCRIPTION QUERY / MUTATION HOOKS
// ============================================================

export const subscriptionKeys = {
  all: ["subscriptions"] as const,
  plans: () => [...subscriptionKeys.all, "plans"] as const,
  me: () => [...subscriptionKeys.all, "me"] as const,
  detail: (id: number) => [...subscriptionKeys.all, "detail", id] as const,
};

/** Active plan catalog. */
export function usePlans() {
  return useQuery<Plan[]>({
    queryKey: subscriptionKeys.plans(),
    queryFn: () => subscriptionService.getPlans(),
  });
}

/** Current user's subscription + entitled features. */
export function useMySubscription() {
  return useQuery<SubscriptionMe>({
    queryKey: subscriptionKeys.me(),
    queryFn: () => subscriptionService.getMySubscription(),
  });
}

/** Start gateway checkout for a plan. Caller redirects to the returned URL. */
export function useSubscribe() {
  const queryClient = useQueryClient();
  return useMutation<
    SubscriptionCheckout,
    unknown,
    { planCode: string; method: "sslcommerz" | "bkash" }
  >({
    mutationFn: ({ planCode, method }) => subscriptionService.checkout(planCode, method),
    onError: (error) => {
      toast.error(getApiErrorMessage(error, "Could not start subscription checkout."));
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: subscriptionKeys.all });
    },
  });
}

/** Cancel at period end. */
export function useCancelSubscription() {
  const queryClient = useQueryClient();
  return useMutation<Subscription, unknown, number>({
    mutationFn: (id) => subscriptionService.cancel(id),
    onError: (error) => {
      toast.error(getApiErrorMessage(error, "Could not cancel the subscription."));
    },
    onSuccess: () => {
      toast.success("Subscription will end at the current period end.");
      queryClient.invalidateQueries({ queryKey: subscriptionKeys.all });
    },
  });
}

/** Start a renewal checkout. */
export function useRenewSubscription() {
  const queryClient = useQueryClient();
  return useMutation<
    SubscriptionCheckout,
    unknown,
    { subscriptionId: number; method: "sslcommerz" | "bkash" }
  >({
    mutationFn: ({ subscriptionId, method }) => subscriptionService.renew(subscriptionId, method),
    onError: (error) => {
      toast.error(getApiErrorMessage(error, "Could not start renewal checkout."));
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: subscriptionKeys.all });
    },
  });
}
