import { api } from "./api";
import type { ReferralInfo } from "../types";

// ============================================================
// REFERRAL SERVICE — /users/referral/ (referral program)
// ============================================================

interface ApiReferralInfo {
  code: string;
  link: string;
  invited_count: number;
  invited: { username: string; joined_at: string }[];
}

export const referralService = {
  async getReferralInfo(): Promise<ReferralInfo> {
    const { data } = await api.get<ApiReferralInfo>("/users/referral/");
    return {
      code: data.code,
      link: data.link,
      invitedCount: data.invited_count,
      invited: data.invited.map((i) => ({ username: i.username, joinedAt: i.joined_at })),
    };
  },
};

export default referralService;
