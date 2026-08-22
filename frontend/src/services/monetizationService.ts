import { api } from "./api";
import type {
  Commission,
  Payout,
  PayoutStatus,
  RevenueDashboard,
  RevenueLedgerEntry,
} from "../types";

// ============================================================
// MONETIZATION SERVICE — admin revenue dashboard + payout queue
// ============================================================

export interface ApiCommission {
  id: number;
  kind: string;
  recipient: number;
  recipient_name: string;
  amount: string | number;
  rate: string | number;
  status: string;
  detail: Record<string, unknown>;
  created_at: string;
  paid_at: string | null;
}

export interface ApiPayout {
  id: number;
  recipient: number;
  recipient_name: string;
  amount: string | number;
  method: string;
  account_details: Record<string, unknown>;
  status: string;
  reference: string;
  reason: string;
  created_at: string;
  decided_at: string | null;
}

interface ApiLedgerEntry {
  id: number;
  entry_type: string;
  scope: string;
  user: number | null;
  gross_amount: string | number;
  platform_amount: string | number;
  partner_amount: string | number;
  currency: string;
  created_at: string;
}

export function mapCommission(api: ApiCommission): Commission {
  return {
    id: api.id,
    kind: api.kind,
    recipient: api.recipient,
    recipientName: api.recipient_name,
    amount: Number(api.amount),
    rate: Number(api.rate),
    status: api.status as Commission["status"],
    detail: api.detail,
    createdAt: api.created_at,
    paidAt: api.paid_at,
  };
}

export function mapPayout(api: ApiPayout): Payout {
  return {
    id: api.id,
    recipient: api.recipient,
    recipientName: api.recipient_name,
    amount: Number(api.amount),
    method: api.method,
    accountDetails: api.account_details,
    status: api.status as Payout["status"],
    reference: api.reference,
    reason: api.reason,
    createdAt: api.created_at,
    decidedAt: api.decided_at,
  };
}

function mapLedger(api: ApiLedgerEntry): RevenueLedgerEntry {
  return {
    id: api.id,
    entryType: api.entry_type,
    scope: api.scope,
    user: api.user,
    grossAmount: Number(api.gross_amount),
    platformAmount: Number(api.platform_amount),
    partnerAmount: Number(api.partner_amount),
    currency: api.currency,
    createdAt: api.created_at,
  };
}

export const monetizationService = {
  /** GET /monetization/revenue/dashboard/ — admin only. */
  async getRevenueDashboard(): Promise<RevenueDashboard> {
    const { data } = await api.get<{
      revenue_by_scope: { scope: string; gross: number | null; platform: number | null }[];
      total_revenue: number | null;
      platform_revenue: number | null;
      mrr: number | null;
      partner_obligations: number | null;
      pending_payouts: { count: number; total: number | null };
      recent_ledger: ApiLedgerEntry[];
      recent_commissions: ApiCommission[];
      recent_payouts: ApiPayout[];
    }>("/monetization/revenue/dashboard/");
    return {
      revenueByScope: data.revenue_by_scope,
      totalRevenue: data.total_revenue != null ? Number(data.total_revenue) : null,
      platformRevenue: data.platform_revenue != null ? Number(data.platform_revenue) : null,
      mrr: data.mrr != null ? Number(data.mrr) : null,
      partnerObligations:
        data.partner_obligations != null ? Number(data.partner_obligations) : null,
      pendingPayouts: {
        count: data.pending_payouts.count,
        total: data.pending_payouts.total != null ? Number(data.pending_payouts.total) : null,
      },
      recentLedger: data.recent_ledger.map(mapLedger),
      recentCommissions: data.recent_commissions.map(mapCommission),
      recentPayouts: data.recent_payouts.map(mapPayout),
    };
  },

  /** GET /monetization/payouts/requests/ — admin list (status filter). */
  async listPayoutRequests(status?: PayoutStatus): Promise<Payout[]> {
    const { data } = await api.get<ApiPayout[]>("/monetization/payouts/requests/", {
      params: status ? { status } : {},
    });
    return data.map(mapPayout);
  },

  /** POST /monetization/payouts/:id/decision/ — approve or reject. */
  async decidePayout(id: number, action: "approve" | "reject", reason = ""): Promise<Payout> {
    const { data } = await api.post<ApiPayout>(`/monetization/payouts/${id}/decision/`, {
      action,
      reason,
    });
    return mapPayout(data);
  },

  /** POST /monetization/payouts/:id/mark-paid/ */
  async markPayoutPaid(id: number, reference = ""): Promise<Payout> {
    const { data } = await api.post<ApiPayout>(`/monetization/payouts/${id}/mark-paid/`, {
      reference,
    });
    return mapPayout(data);
  },
};

export default monetizationService;
