import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { roommateService } from "../services/roommateService";
import type { RoommateProfilePayload } from "../types";

// ============================================================
// ROOMMATE QUERY HOOKS
// ============================================================

const BASE = ["roommates"] as const;

export const roommateKeys = {
  all: BASE,
  profile: [...BASE, "profile"] as const,
  matches: [...BASE, "matches"] as const,
  requests: [...BASE, "requests"] as const,
};

/** The caller's own profile — null until they create one. */
export function useRoommateProfile() {
  return useQuery({
    queryKey: roommateKeys.profile,
    queryFn: () => roommateService.getMyProfile(),
    retry: false,
  });
}

/** Best-first scored match suggestions. */
export function useRoommateMatches(enabled: boolean) {
  return useQuery({
    queryKey: roommateKeys.matches,
    queryFn: () => roommateService.getMatches(),
    enabled,
    retry: false,
  });
}

/** My roommate requests (incoming + outgoing). */
export function useRoommateRequests(enabled: boolean) {
  return useQuery({
    queryKey: roommateKeys.requests,
    queryFn: () => roommateService.getMyRequests(),
    enabled,
    retry: false,
  });
}

/** Create or update my roommate profile. */
export function useSaveRoommateProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: RoommateProfilePayload) => roommateService.saveMyProfile(payload),
    onSuccess: () => {
      queryClient.setQueryData(roommateKeys.profile, null);
      queryClient.invalidateQueries({ queryKey: roommateKeys.profile });
      queryClient.invalidateQueries({ queryKey: roommateKeys.matches });
      toast.success("Roommate profile saved!");
    },
  });
}

/** Send a roommate request to another user. */
export function useSendRoommateRequest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ receiverId, message }: { receiverId: number; message: string }) =>
      roommateService.sendRequest(receiverId, message),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: roommateKeys.requests });
      queryClient.invalidateQueries({ queryKey: roommateKeys.matches });
      toast.success("Roommate request sent!");
    },
    onError: (error: { response?: { data?: { errors?: string[] } } }) => {
      const errors = error.response?.data?.errors;
      if (errors?.length) toast.error(errors[0]);
    },
  });
}

/** Approve or reject an incoming roommate request. */
export function useRespondRoommateRequest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ requestId, action }: { requestId: number; action: "approve" | "reject" }) =>
      roommateService.respondToRequest(requestId, action),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: roommateKeys.requests });
      queryClient.invalidateQueries({ queryKey: roommateKeys.matches });
      queryClient.invalidateQueries({ queryKey: roommateKeys.profile });
      toast.success(
        variables.action === "approve" ? "You found a roommate! 🎉" : "Request rejected."
      );
    },
  });
}
