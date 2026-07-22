import { api } from "./api";
import type { DashboardStats } from "../types";

// ============================================================
// DASHBOARD SERVICE — real /dashboard/ endpoints
// ============================================================

export const dashboardService = {
  /** GET /dashboard/stats/ → aggregated stats for the current user. */
  async getStats(): Promise<DashboardStats> {
    const { data } = await api.get<DashboardStats>("/dashboard/stats/");
    return data;
  },
};

export default dashboardService;
