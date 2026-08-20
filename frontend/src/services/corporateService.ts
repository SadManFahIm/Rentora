import { api } from "./api";
import type { CorporateAccount, CorporateInvoice, CorporateMember } from "../types";

// ============================================================
// CORPORATE SERVICE — corporate housing accounts & bulk booking
// ============================================================

interface ApiCorporateAccount {
  id: number;
  name: string;
  email: string;
  phone: string;
  address: string;
  vat_number: string;
  owner: number;
  owner_name: string;
  status: string;
  created_at: string;
}

interface ApiCorporateMember {
  id: number;
  account: number;
  user: number;
  user_name: string;
  email: string;
  role: string;
  created_at: string;
}

interface ApiCorporateInvoice {
  id: number;
  account: number;
  account_name: string;
  invoice_number: string;
  period_start: string;
  period_end: string;
  amount: string | number;
  status: string;
  line_items: Record<string, unknown>[];
  created_at: string;
}

export function mapCorporateAccount(api: ApiCorporateAccount): CorporateAccount {
  return {
    id: api.id,
    name: api.name,
    email: api.email,
    phone: api.phone,
    address: api.address,
    vatNumber: api.vat_number,
    owner: api.owner,
    ownerName: api.owner_name,
    status: api.status as CorporateAccount["status"],
    createdAt: api.created_at,
  };
}

function mapMember(api: ApiCorporateMember): CorporateMember {
  return {
    id: api.id,
    account: api.account,
    user: api.user,
    userName: api.user_name,
    email: api.email,
    role: api.role as CorporateMember["role"],
    createdAt: api.created_at,
  };
}

function mapInvoice(api: ApiCorporateInvoice): CorporateInvoice {
  return {
    id: api.id,
    account: api.account,
    accountName: api.account_name,
    invoiceNumber: api.invoice_number,
    periodStart: api.period_start,
    periodEnd: api.period_end,
    amount: Number(api.amount),
    status: api.status as CorporateInvoice["status"],
    lineItems: api.line_items,
    createdAt: api.created_at,
  };
}

export interface BulkBookingRequest {
  roomId: number;
  memberIds: number[];
  dateFrom: string;
  dateTo: string;
}

export const corporateService = {
  /** GET /corporate/accounts/ — own accounts. */
  async listAccounts(): Promise<CorporateAccount[]> {
    const { data } = await api.get<ApiCorporateAccount[]>("/corporate/accounts/");
    return data.map(mapCorporateAccount);
  },

  /** POST /corporate/accounts/ */
  async createAccount(input: {
    name: string;
    email: string;
    phone: string;
    address: string;
    vatNumber?: string;
  }): Promise<CorporateAccount> {
    const { data } = await api.post<ApiCorporateAccount>("/corporate/accounts/", {
      name: input.name,
      email: input.email,
      phone: input.phone,
      address: input.address,
      vat_number: input.vatNumber ?? "",
    });
    return mapCorporateAccount(data);
  },

  /** GET /corporate/accounts/:id/ */
  async getAccount(id: number): Promise<CorporateAccount> {
    const { data } = await api.get<ApiCorporateAccount>(`/corporate/accounts/${id}/`);
    return mapCorporateAccount(data);
  },

  /** GET /corporate/accounts/:id/members/ */
  async listMembers(accountId: number): Promise<CorporateMember[]> {
    const { data } = await api.get<ApiCorporateMember[]>(
      `/corporate/accounts/${accountId}/members/`
    );
    return data.map(mapMember);
  },

  /** POST /corporate/accounts/:id/members/ — invite members by email. */
  async addMembers(accountId: number, emails: string[]): Promise<CorporateMember[]> {
    const { data } = await api.post<ApiCorporateMember[]>(
      `/corporate/accounts/${accountId}/members/`,
      {
        emails,
      }
    );
    return data.map(mapMember);
  },

  /** POST /corporate/bulk-booking/ — one request, many members. */
  async bulkBooking(request: BulkBookingRequest): Promise<{ succeeded: number; failed: number }> {
    const { data } = await api.post<{ succeeded: number; failed: number }>(
      "/corporate/bulk-booking/",
      {
        room_id: request.roomId,
        member_ids: request.memberIds,
        date_from: request.dateFrom,
        date_to: request.dateTo,
      }
    );
    return data;
  },

  /** GET /corporate/invoices/ — own invoices. */
  async listInvoices(): Promise<CorporateInvoice[]> {
    const { data } = await api.get<ApiCorporateInvoice[]>("/corporate/invoices/");
    return data.map(mapInvoice);
  },

  /** POST /corporate/invoices/:id/generate/ — finalize a draft invoice. */
  async generateInvoice(id: number): Promise<CorporateInvoice> {
    const { data } = await api.post<ApiCorporateInvoice>(`/corporate/invoices/${id}/generate/`, {});
    return mapInvoice(data);
  },

  /** GET /corporate/admin/overview/ — company admins. */
  async adminOverview(): Promise<{
    accounts: CorporateAccount[];
    pendingAccounts: number;
    totalMembers: number;
  }> {
    const { data } = await api.get<{
      accounts: ApiCorporateAccount[];
      pending_accounts: number;
      total_members: number;
    }>("/corporate/admin/overview/");
    return {
      accounts: data.accounts.map(mapCorporateAccount),
      pendingAccounts: data.pending_accounts,
      totalMembers: data.total_members,
    };
  },

  /** POST /corporate/admin/accounts/:id/action/ — approve/suspend/reactivate. */
  async adminAction(
    id: number,
    action: "approve" | "suspend" | "reactivate"
  ): Promise<CorporateAccount> {
    const { data } = await api.post<ApiCorporateAccount>(
      `/corporate/admin/accounts/${id}/action/`,
      {
        action,
      }
    );
    return mapCorporateAccount(data);
  },
};

export default corporateService;
