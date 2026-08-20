import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { fraudService } from "../services/fraudService";

// ============================================================
// FRAUD QUERY HOOKS
// ============================================================

export const fraudKeys = {
  all: ["fraud"] as const,
  status: (roomId: number) => [...fraudKeys.all, "status", roomId] as const,
  reports: (params: Record<string, string> = {}) => [...fraudKeys.all, "reports", params] as const,
};

/** Public fraud status for a single room — drives the "under review" badge. */
export function useRoomFraudStatus(roomId: number | null) {
  return useQuery({
    queryKey: fraudKeys.status(roomId ?? -1),
    queryFn: () => fraudService.getRoomStatus(roomId as number),
    enabled: roomId != null,
    retry: false,
  });
}

/** Fraud reports for my listings (admin sees all), with optional filters. */
export function useFraudReports(
  params: {
    status?: string;
    severity?: string;
    area?: string;
    detector?: string;
    q?: string;
    ordering?: string;
  } = {}
) {
  const { data, ...rest } = useQuery({
    queryKey: fraudKeys.reports(params),
    queryFn: () => fraudService.getReports(params),
    retry: false,
  });
  return { data: data ?? [], ...rest };
}

/** Admin-only fraud dashboard summary. */
export function useFraudSummary() {
  return useQuery({
    queryKey: [...fraudKeys.all, "summary"] as const,
    queryFn: () => fraudService.getSummary(),
    retry: false,
  });
}

/** Admin-only append-only fraud audit trail. */
export function useFraudAuditLog() {
  return useQuery({
    queryKey: [...fraudKeys.all, "audit"] as const,
    queryFn: () => fraudService.getAuditLog(),
    retry: false,
  });
}

/** Phase 15 — D8: admin-only coordinated-account rings (review queue). */
export function useFraudRings() {
  return useQuery({
    queryKey: [...fraudKeys.all, "rings"] as const,
    queryFn: () => fraudService.getRings(),
    retry: false,
  });
}

/** Re-scan a room (owner/admin). */
export function useScanRoom() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (roomId: number) => fraudService.scanRoom(roomId),
    onSuccess: (report) => {
      queryClient.invalidateQueries({ queryKey: fraudKeys.all });
      toast.success(
        report.severity === "clean"
          ? "Scan complete — no risk signals."
          : `Scan complete — ${report.severity.toUpperCase()} risk (${report.score}/100).`
      );
    },
  });
}

/** Admin review/dismiss of a report. */
export function useReviewFraudReport() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ reportId, action }: { reportId: number; action: "reviewed" | "dismissed" }) =>
      fraudService.reviewReport(reportId, action),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: fraudKeys.all });
      toast.success("Report updated.");
    },
  });
}
