import { api } from "./api";
import {
  mapPayout,
  mapCommission,
  type ApiPayout,
  type ApiCommission,
} from "./monetizationService";
import type {
  BrokerDashboard,
  BrokerProfile,
  BrokerVerification,
  Commission,
  Payout,
} from "../types";

// ============================================================
// BROKER SERVICE — broker network (register, dashboard, payouts)
// ============================================================

interface ApiBrokerProfile {
  id: number;
  user: number;
  user_name: string;
  license_number: string;
  years_experience: number;
  specialization: string;
  areas: string[];
  referral_code: string;
  status: string;
  is_verified: boolean;
  created_at: string;
}

interface ApiBrokerVerification {
  id: number;
  profile: number;
  documents: string[];
  notes: string;
  status: string;
  auto_screen_score: number | null;
  auto_screen_result: string | null;
  auto_screen_detail: Record<string, unknown>;
  created_at: string;
}

export function mapBrokerProfile(api: ApiBrokerProfile): BrokerProfile {
  return {
    id: api.id,
    user: api.user,
    userName: api.user_name,
    licenseNumber: api.license_number,
    yearsExperience: api.years_experience,
    specialization: api.specialization,
    areas: api.areas,
    referralCode: api.referral_code,
    status: api.status as BrokerProfile["status"],
    isVerified: api.is_verified,
    createdAt: api.created_at,
  };
}

function mapVerification(api: ApiBrokerVerification): BrokerVerification {
  return {
    id: api.id,
    profile: api.profile,
    documents: api.documents,
    notes: api.notes,
    status: api.status as BrokerVerification["status"],
    autoScreenScore: api.auto_screen_score,
    autoScreenResult: api.auto_screen_result,
    autoScreenDetail: api.auto_screen_detail,
    createdAt: api.created_at,
  };
}

export const brokerService = {
  /** GET /brokers/profile/ */
  async getProfile(): Promise<BrokerProfile> {
    const { data } = await api.get<ApiBrokerProfile>("/brokers/profile/");
    return mapBrokerProfile(data);
  },

  /** PUT /brokers/profile/ */
  async updateProfile(
    fields: Partial<
      Pick<BrokerProfile, "licenseNumber" | "yearsExperience" | "specialization" | "areas">
    >
  ): Promise<BrokerProfile> {
    const payload: Record<string, unknown> = {};
    if (fields.licenseNumber !== undefined) payload.license_number = fields.licenseNumber;
    if (fields.yearsExperience !== undefined) payload.years_experience = fields.yearsExperience;
    if (fields.specialization !== undefined) payload.specialization = fields.specialization;
    if (fields.areas !== undefined) payload.areas = fields.areas;
    const { data } = await api.put<ApiBrokerProfile>("/brokers/profile/", payload);
    return mapBrokerProfile(data);
  },

  /** POST /brokers/register/ — submit profile + first verification. */
  async register(input: {
    licenseNumber: string;
    yearsExperience: number;
    specialization: string;
    areas: string[];
    documents: string[];
    notes?: string;
  }): Promise<{ profile: BrokerProfile; verification: BrokerVerification }> {
    const { data } = await api.post<{
      profile: ApiBrokerProfile;
      verification: ApiBrokerVerification;
    }>("/brokers/register/", {
      license_number: input.licenseNumber,
      years_experience: input.yearsExperience,
      specialization: input.specialization,
      areas: input.areas,
      documents: input.documents,
      notes: input.notes ?? "",
    });
    return {
      profile: mapBrokerProfile(data.profile),
      verification: mapVerification(data.verification),
    };
  },

  /** GET /brokers/dashboard/ */
  async getDashboard(): Promise<BrokerDashboard> {
    const { data } = await api.get<{
      profile: ApiBrokerProfile;
      available_balance: string | number;
      summary: { pending_count: number; pending_total: number; paid_total: number };
      recent_commissions: ApiCommission[];
      share_url: string;
    }>("/brokers/dashboard/");
    return {
      profile: mapBrokerProfile(data.profile),
      availableBalance: Number(data.available_balance),
      summary: {
        pendingCount: data.summary.pending_count,
        pendingTotal: Number(data.summary.pending_total),
        paidTotal: Number(data.summary.paid_total),
      },
      recentCommissions: data.recent_commissions.map(mapCommission),
      shareUrl: data.share_url,
    };
  },

  /** GET /brokers/commissions/ — own commissions (optional status filter). */
  async listCommissions(status?: string): Promise<Commission[]> {
    const { data } = await api.get<ApiCommission[]>("/brokers/commissions/", {
      params: status ? { status } : {},
    });
    return data.map(mapCommission);
  },

  /** GET /brokers/payouts/ — own payout requests. */
  async listPayouts(): Promise<Payout[]> {
    const { data } = await api.get<ApiPayout[]>("/brokers/payouts/");
    return data.map(mapPayout);
  },

  /** POST /brokers/payouts/request/ */
  async requestPayout(
    amount: number,
    method: string,
    accountDetails: Record<string, unknown> = {}
  ): Promise<Payout> {
    const { data } = await api.post<ApiPayout>("/brokers/payouts/request/", {
      amount,
      method,
      account_details: accountDetails,
    });
    return mapPayout(data);
  },
};

export default brokerService;
