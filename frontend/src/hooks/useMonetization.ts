import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { monetizationService } from "../services/monetizationService";
import { getApiErrorMessage } from "../services/errors";
import type { Payout, PayoutStatus, RevenueDashboard } from "../types";

// ============================================================
// MONETIZATION HOOKS — admin revenue dashboard + payout queue
// ============================================================

export const monetizationKeys = {
  all: ["monetization"] as const,
  dashboard: () => [...monetizationKeys.all, "dashboard"] as const,
  payouts: (status?: PayoutStatus) =>
    [...monetizationKeys.all, "payouts", status ?? "all"] as const,
  payout: (id: number) => [...monetizationKeys.all, "payout", id] as const,
};

/** Admin-only revenue dashboard. */
export function useRevenueDashboard(enabled = true) {
  return useQuery<RevenueDashboard>({
    queryKey: monetizationKeys.dashboard(),
    queryFn: () => monetizationService.getRevenueDashboard(),
    enabled,
  });
}

/** Admin payout request queue, optionally filtered by status. */
export function usePayoutRequests(status?: PayoutStatus) {
  return useQuery<Payout[]>({
    queryKey: monetizationKeys.payouts(status),
    queryFn: () => monetizationService.listPayoutRequests(status),
  });
}

/** Approve or reject a payout request. */
export function useDecidePayout() {
  const queryClient = useQueryClient();
  return useMutation<
    Payout,
    unknown,
    { id: number; action: "approve" | "reject"; reason?: string }
  >({
    mutationFn: ({ id, action, reason = "" }) =>
      monetizationService.decidePayout(id, action, reason),
    onError: (error) => {
      toast.error(getApiErrorMessage(error, "Could not update the payout request."));
    },
    onSuccess: (_payout, vars) => {
      toast.success(`Payout request ${vars.action === "approve" ? "approved" : "rejected"}.`);
      queryClient.invalidateQueries({ queryKey: monetizationKeys.all });
    },
  });
}

/** Mark an approved payout as paid (offline settlement recorded). */
export function useMarkPayoutPaid() {
  const queryClient = useQueryClient();
  return useMutation<Payout, unknown, { id: number; reference?: string }>({
    mutationFn: ({ id, reference = "" }) => monetizationService.markPayoutPaid(id, reference),
    onError: (error) => {
      toast.error(getApiErrorMessage(error, "Could not mark the payout as paid."));
    },
    onSuccess: () => {
      toast.success("Payout marked as paid.");
      queryClient.invalidateQueries({ queryKey: monetizationKeys.all });
    },
  });
}
