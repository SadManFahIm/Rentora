import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { brokerService } from "../services/brokerService";
import { getApiErrorMessage } from "../services/errors";
import type { BrokerDashboard, BrokerProfile, Payout } from "../types";

// ============================================================
// BROKER QUERY / MUTATION HOOKS
// ============================================================

export const brokerKeys = {
  all: ["brokers"] as const,
  profile: () => [...brokerKeys.all, "profile"] as const,
  dashboard: () => [...brokerKeys.all, "dashboard"] as const,
  commissions: () => [...brokerKeys.all, "commissions"] as const,
  payouts: () => [...brokerKeys.all, "payouts"] as const,
};

/** The user's broker profile (if they have applied). */
export function useBrokerProfile() {
  return useQuery<BrokerProfile>({
    queryKey: brokerKeys.profile(),
    queryFn: () => brokerService.getProfile(),
    retry: false,
  });
}

/** Broker dashboard: balance + summary + recent commissions. */
export function useBrokerDashboard() {
  return useQuery<BrokerDashboard>({
    queryKey: brokerKeys.dashboard(),
    queryFn: () => brokerService.getDashboard(),
  });
}

interface RegisterBrokerInput {
  licenseNumber: string;
  yearsExperience: number;
  specialization: string;
  areas: string[];
  documents: string[];
  notes?: string;
}

/** Submit a broker application (creates profile + first verification). */
export function useRegisterBroker() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: RegisterBrokerInput) => brokerService.register(input),
    onError: (error) => {
      toast.error(getApiErrorMessage(error, "Could not submit the broker application."));
    },
    onSuccess: () => {
      toast.success("Broker application submitted — verification pending.");
      queryClient.invalidateQueries({ queryKey: brokerKeys.all });
    },
  });
}

/** Update own broker profile details. */
export function useUpdateBrokerProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (fields: Parameters<typeof brokerService.updateProfile>[0]) =>
      brokerService.updateProfile(fields),
    onError: (error) => {
      toast.error(getApiErrorMessage(error, "Could not update the broker profile."));
    },
    onSuccess: () => {
      toast.success("Broker profile updated.");
      queryClient.invalidateQueries({ queryKey: brokerKeys.all });
    },
  });
}

/** Request a payout of earned commissions. */
export function useRequestPayout() {
  const queryClient = useQueryClient();
  return useMutation<
    Payout,
    unknown,
    { amount: number; method: string; accountDetails?: Record<string, unknown> }
  >({
    mutationFn: ({ amount, method, accountDetails = {} }) =>
      brokerService.requestPayout(amount, method, accountDetails),
    onError: (error) => {
      toast.error(getApiErrorMessage(error, "Could not request the payout."));
    },
    onSuccess: () => {
      toast.success("Payout requested — pending admin review.");
      queryClient.invalidateQueries({ queryKey: brokerKeys.all });
    },
  });
}
