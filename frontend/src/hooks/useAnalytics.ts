import { useQuery } from "@tanstack/react-query";

import { fetchAnalyticsSummary } from "../services/analytics";

/** Admin-only product-usage summary (totals, funnel, top events/pages). */
export function useAnalyticsSummary(days = 30) {
  return useQuery({
    queryKey: ["analytics-summary", days],
    queryFn: () => fetchAnalyticsSummary(days),
    staleTime: 60_000,
  });
}
