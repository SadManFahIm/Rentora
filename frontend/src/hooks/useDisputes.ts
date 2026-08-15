import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  disputeService,
  type ActOnDisputePayload,
  type AddEvidencePayload,
  type CreateDisputePayload,
} from "../services/disputeService";
import type { Dispute } from "../types";

export const disputeKeys = {
  all: ["disputes"] as const,
  list: () => [...disputeKeys.all, "list"] as const,
  detail: (id: number) => [...disputeKeys.all, "detail", id] as const,
  admin: (status: string) => [...disputeKeys.all, "admin", status] as const,
};

export function useDisputes() {
  return useQuery<Dispute[]>({
    queryKey: disputeKeys.list(),
    queryFn: () => disputeService.getDisputes(),
  });
}

export function useDispute(id: number | null) {
  return useQuery<Dispute>({
    queryKey: disputeKeys.detail(id ?? -1),
    queryFn: () => disputeService.getDispute(id as number),
    enabled: id != null,
  });
}

export function useCreateDispute() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreateDisputePayload) => disputeService.createDispute(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: disputeKeys.all });
    },
  });
}

export function useAddDisputeEvidence() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: AddEvidencePayload }) =>
      disputeService.addEvidence(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: disputeKeys.all });
    },
  });
}

export function useAdminDisputes(status = "open") {
  return useQuery<Dispute[]>({
    queryKey: disputeKeys.admin(status),
    queryFn: () => disputeService.getAdminDisputes(status),
  });
}

export function useActOnDispute() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: ActOnDisputePayload }) =>
      disputeService.actOnDispute(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: disputeKeys.all });
    },
  });
}
