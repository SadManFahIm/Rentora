import { useQuery } from "@tanstack/react-query";
import { dashboardService } from "../services/dashboardService";
import type { DashboardStats } from "../types";

// ============================================================
// DASHBOARD HOOK
// ============================================================

export const dashboardKeys = {
  stats: ["dashboard", "stats"] as const,
};

/** Fetch the authenticated user's dashboard statistics. */
export function useDashboard() {
  return useQuery<DashboardStats>({
    queryKey: dashboardKeys.stats,
    queryFn: () => dashboardService.getStats(),
    staleTime: 30_000,
  });
}
