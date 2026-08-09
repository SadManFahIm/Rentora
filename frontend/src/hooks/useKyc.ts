import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { kycService } from "../services/kycService";
import type { KycApplication, KycAuditEntry, KycDocType, KycDocument } from "../types";

// ============================================================
// KYC HOOKS — my documents + admin review panel
// ============================================================

export const kycKeys = {
  all: ["kyc"] as const,
  mine: () => [...kycKeys.all, "mine"] as const,
  pending: () => [...kycKeys.all, "pending"] as const,
  audit: () => [...kycKeys.all, "audit"] as const,
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

/** Admin-only KYC decision history (append-only audit trail). */
export function useKycAuditTrail() {
  return useQuery<KycAuditEntry[]>({
    queryKey: kycKeys.audit(),
    queryFn: () => kycService.auditTrail(),
  });
}
