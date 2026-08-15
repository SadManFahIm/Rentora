import { useQuery } from "@tanstack/react-query";
import { auditService } from "../services/auditService";
import type { AuditEntry } from "../types";

export function useAuditTrail(prefix?: string) {
  return useQuery<AuditEntry[]>({
    queryKey: ["audit", prefix ?? "all"],
    queryFn: () => auditService.getTrail(prefix),
  });
}
