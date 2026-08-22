import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { partnerService } from "../services/partnerService";
import { getApiErrorMessage } from "../services/errors";
import type { CreditEligibility, InsuranceProduct, InsuranceQuote } from "../types";

// ============================================================
// INSURANCE / CREDIT PARTNER HOOKS
// ============================================================

export const insuranceKeys = {
  all: ["insurance"] as const,
  products: () => [...insuranceKeys.all, "products"] as const,
  quotes: () => [...insuranceKeys.all, "quotes"] as const,
  credit: () => [...insuranceKeys.all, "credit"] as const,
};

/** Insurance product catalog (partner services). */
export function useInsuranceProducts() {
  return useQuery<InsuranceProduct[]>({
    queryKey: insuranceKeys.products(),
    queryFn: () => partnerService.listInsuranceProducts(),
  });
}

/** Own insurance quotes. */
export function useInsuranceQuotes() {
  return useQuery<InsuranceQuote[]>({
    queryKey: insuranceKeys.quotes(),
    queryFn: () => partnerService.listQuotes(),
  });
}

/** Request a quote for a product. */
export function useCreateInsuranceQuote() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (vars: { productId: number; coveragePeriod: number }) =>
      partnerService.createQuote(vars.productId, vars.coveragePeriod),
    onError: (error) => {
      toast.error(getApiErrorMessage(error, "Could not request the quote."));
    },
    onSuccess: () => {
      toast.success("Quote requested.");
      queryClient.invalidateQueries({ queryKey: insuranceKeys.quotes() });
    },
  });
}

/** Act on a quote (issue/decline/cancel). */
export function useInsuranceQuoteAction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (vars: { id: number; action: "issue" | "decline" | "cancel" }) =>
      partnerService.quoteAction(vars.id, vars.action),
    onError: (error) => {
      toast.error(getApiErrorMessage(error, "Could not update the quote."));
    },
    onSuccess: (_quote, vars) => {
      toast.success(`Quote ${vars.action}ed.`);
      queryClient.invalidateQueries({ queryKey: insuranceKeys.all });
    },
  });
}

/** Renter credit eligibility (pre-approved limit). */
export function useCreditEligibility(enabled = true) {
  return useQuery<CreditEligibility>({
    queryKey: insuranceKeys.credit(),
    queryFn: () => partnerService.creditEligibility(),
    enabled,
  });
}
