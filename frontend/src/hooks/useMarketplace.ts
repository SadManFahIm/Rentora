import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { marketplaceService } from "../services/marketplaceService";
import { getApiErrorMessage } from "../services/errors";
import type { AddonOrder, AddonProvider, AddonService, MarketplaceRecommendation } from "../types";

// ============================================================
// MARKETPLACE QUERY / MUTATION HOOKS
// ============================================================

export const marketplaceKeys = {
  all: ["marketplace"] as const,
  services: (category?: string) => [...marketplaceKeys.all, "services", category ?? "all"] as const,
  service: (id: number) => [...marketplaceKeys.all, "service", id] as const,
  orders: () => [...marketplaceKeys.all, "orders"] as const,
  recommendations: (bookingId?: number) =>
    [...marketplaceKeys.all, "recommendations", bookingId ?? "all"] as const,
  provider: () => [...marketplaceKeys.all, "provider"] as const,
};

/** Add-on service catalog, optionally filtered by category. */
export function useAddonServices(category?: string) {
  return useQuery<AddonService[]>({
    queryKey: marketplaceKeys.services(category),
    queryFn: () => marketplaceService.listServices(category),
  });
}

/** Own add-on orders. */
export function useAddonOrders() {
  return useQuery<AddonOrder[]>({
    queryKey: marketplaceKeys.orders(),
    queryFn: () => marketplaceService.listOrders(),
  });
}

/** AI add-on recommendations for a booking. */
export function useAddonRecommendations(bookingId?: number) {
  return useQuery<MarketplaceRecommendation[]>({
    queryKey: marketplaceKeys.recommendations(bookingId),
    queryFn: () => marketplaceService.recommend(bookingId as number),
    enabled: bookingId != null,
  });
}

/** The user's provider business profile (if registered). */
export function useProviderMe() {
  return useQuery<AddonProvider>({
    queryKey: marketplaceKeys.provider(),
    queryFn: () => marketplaceService.getProviderMe(),
    retry: false,
  });
}

/** Place an add-on order. */
export function useCreateAddonOrder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (vars: { serviceId: number; quantity?: number; notes?: string }) =>
      marketplaceService.createOrder(vars.serviceId, vars.quantity ?? 1, vars.notes ?? ""),
    onError: (error) => {
      toast.error(getApiErrorMessage(error, "Could not place the order."));
    },
    onSuccess: () => {
      toast.success("Order placed.");
      queryClient.invalidateQueries({ queryKey: marketplaceKeys.orders() });
    },
  });
}

/** Provider acts on an order (confirm/cancel/complete). */
export function useAddonOrderAction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (vars: { id: number; action: "confirm" | "cancel" | "complete" }) =>
      marketplaceService.orderAction(vars.id, vars.action),
    onError: (error) => {
      toast.error(getApiErrorMessage(error, "Could not update the order."));
    },
    onSuccess: (_order, vars) => {
      toast.success(`Order ${vars.action}ed.`);
      queryClient.invalidateQueries({ queryKey: marketplaceKeys.all });
    },
  });
}

/** Register a service-provider business. */
export function useRegisterProvider() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { businessName: string; description: string }) =>
      marketplaceService.registerProvider(input),
    onError: (error) => {
      toast.error(getApiErrorMessage(error, "Could not register the business."));
    },
    onSuccess: () => {
      toast.success("Business registered.");
      queryClient.invalidateQueries({ queryKey: marketplaceKeys.provider() });
    },
  });
}
