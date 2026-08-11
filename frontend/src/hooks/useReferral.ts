import { useQuery } from "@tanstack/react-query";
import referralService from "../services/referralService";

// ============================================================
// REFERRAL HOOK — referral code, link and invited stats
// ============================================================

export function useReferral() {
  return useQuery({
    queryKey: ["referral"],
    queryFn: referralService.getReferralInfo,
    retry: 1,
  });
}
