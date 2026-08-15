import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { kycService } from "../services/kycService";
import type {
  KycApplication,
  KycAuditEntry,
  KycDocType,
  KycDocument,
  KycSla,
  TenantKycApplication,
  TenantKycDecision,
  TenantVerification,
} from "../types";

// ============================================================
// KYC HOOKS — my documents + admin review panel
// ============================================================

export const kycKeys = {
  all: ["kyc"] as const,
  mine: () => [...kycKeys.all, "mine"] as const,
  pending: () => [...kycKeys.all, "pending"] as const,
  audit: () => [...kycKeys.all, "audit"] as const,
  sla: () => [...kycKeys.all, "sla"] as const,
  // Tenant KYC (Phase 12 — two-sided trust).
  tenantMine: () => [...kycKeys.all, "tenant-mine"] as const,
  tenantPending: () => [...kycKeys.all, "tenant-pending"] as const,
};

/** The caller's own KYC documents. */
export function useMyKycDocuments() {
  return useQuery<KycDocument[]>({
    queryKey: kycKeys.mine(),
    queryFn: () => kycService.myDocuments(),
  });
}

/** Upload a KYC document; refreshes the owner's document list. */
export function useUploadKycDocument() {
  const queryClient = useQueryClient();
  return useMutation<KycDocument, Error, { docType: KycDocType; file: File }>({
    mutationFn: ({ docType, file }) => kycService.uploadDocument(docType, file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: kycKeys.all });
    },
  });
}

/** Admin review queue of pending KYC applications. */
export function usePendingKycApplications() {
  return useQuery<KycApplication[]>({
    queryKey: kycKeys.pending(),
    queryFn: () => kycService.pendingApplications(),
  });
}

/** Admin approve/reject; refreshes the queue + audit trail. */
export function useReviewKycApplication() {
  const queryClient = useQueryClient();
  return useMutation<KycApplication, Error, { userId: number; approved: boolean; note?: string }>({
    mutationFn: ({ userId, approved, note }) =>
      kycService.reviewApplication(userId, approved, note ?? ""),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: kycKeys.all });
    },
  });
}

/** Admin-only KYC review SLA stats (queue health + decision trend). */
export function useKycSla() {
  return useQuery<KycSla>({
    queryKey: kycKeys.sla(),
    queryFn: () => kycService.slaStats(),
  });
}

/** Admin-only KYC decision history (append-only audit trail). */
export function useKycAuditTrail() {
  return useQuery<KycAuditEntry[]>({
    queryKey: kycKeys.audit(),
    queryFn: () => kycService.auditTrail(),
  });
}

// ============================================================
// TENANT KYC HOOKS (Phase 12 — two-sided trust)
// ============================================================

/** The caller's own tenant-verification record (null when never started). */
export function useMyTenantVerification() {
  return useQuery<TenantVerification | null>({
    queryKey: kycKeys.tenantMine(),
    queryFn: () => kycService.myTenantVerification(),
  });
}

/** Submit (or re-submit) a tenant identity document; refreshes the record. */
export function useSubmitTenantVerification() {
  const queryClient = useQueryClient();
  return useMutation<TenantVerification, Error, { docType: KycDocType; file: File }>({
    mutationFn: ({ docType, file }) => kycService.submitTenantVerification(docType, file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: kycKeys.all });
    },
  });
}

/** Admin review queue of pending tenant verifications. */
export function usePendingTenantKycApplications() {
  return useQuery<TenantKycApplication[]>({
    queryKey: kycKeys.tenantPending(),
    queryFn: () => kycService.pendingTenantApplications(),
  });
}

/** Admin decision on a tenant verification; refreshes the tenant queue. */
export function useReviewTenantKycApplication() {
  const queryClient = useQueryClient();
  return useMutation<
    TenantKycApplication,
    Error,
    { userId: number; decision: TenantKycDecision; note?: string }
  >({
    mutationFn: ({ userId, decision, note }) =>
      kycService.reviewTenantApplication(userId, decision, note ?? ""),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: kycKeys.all });
    },
  });
}
