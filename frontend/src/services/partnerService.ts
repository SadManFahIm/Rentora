import { api } from "./api";
import type { CreditEligibility, InsuranceProduct, InsuranceQuote } from "../types";

// ============================================================
// PARTNER SERVICE — insurance products/quotes + credit eligibility
// ============================================================

interface ApiInsuranceProduct {
  id: number;
  partner: number;
  partner_name: string;
  code: string;
  name: string;
  coverage: Record<string, unknown>;
  price_monthly: string | number;
  deductible: string | number;
  is_active: boolean;
}

interface ApiInsuranceQuote {
  id: number;
  product: ApiInsuranceProduct;
  price: string | number;
  coverage_period: number;
  status: string;
  status_display: string;
  quote_data: Record<string, unknown>;
  created_at: string;
}

export function mapInsuranceProduct(api: ApiInsuranceProduct): InsuranceProduct {
  return {
    id: api.id,
    partner: api.partner,
    partnerName: api.partner_name,
    code: api.code,
    name: api.name,
    coverage: api.coverage,
    priceMonthly: Number(api.price_monthly),
    deductible: Number(api.deductible),
    isActive: api.is_active,
  };
}

function mapQuote(api: ApiInsuranceQuote): InsuranceQuote {
  return {
    id: api.id,
    product: mapInsuranceProduct(api.product),
    price: Number(api.price),
    coveragePeriod: api.coverage_period,
    status: api.status as InsuranceQuote["status"],
    statusDisplay: api.status_display,
    quoteData: api.quote_data,
    createdAt: api.created_at,
  };
}

export const partnerService = {
  /** GET /partner-services/insurance/products/ */
  async listInsuranceProducts(): Promise<InsuranceProduct[]> {
    const { data } = await api.get<ApiInsuranceProduct[]>("/partner-services/insurance/products/");
    return data.map(mapInsuranceProduct);
  },

  /** GET /partner-services/insurance/quotes/ — own quotes. */
  async listQuotes(): Promise<InsuranceQuote[]> {
    const { data } = await api.get<ApiInsuranceQuote[]>("/partner-services/insurance/quotes/");
    return data.map(mapQuote);
  },

  /** POST /partner-services/insurance/quotes/ — request a quote. */
  async createQuote(productId: number, coveragePeriod: number): Promise<InsuranceQuote> {
    const { data } = await api.post<ApiInsuranceQuote>("/partner-services/insurance/quotes/", {
      product_id: productId,
      coverage_period: coveragePeriod,
    });
    return mapQuote(data);
  },

  /** POST /partner-services/insurance/quotes/:id/action/ */
  async quoteAction(id: number, action: "issue" | "decline" | "cancel"): Promise<InsuranceQuote> {
    const { data } = await api.post<ApiInsuranceQuote>(
      `/partner-services/insurance/quotes/${id}/action/`,
      { action }
    );
    return mapQuote(data);
  },

  /** GET /partner-services/insurance/credit-eligibility/ */
  async creditEligibility(): Promise<CreditEligibility> {
    const { data } = await api.get<{
      eligible: boolean;
      credit_score: number;
      preapproved_limit: string | number;
      currency: string;
      reasons: string[];
      provider: string;
    }>("/partner-services/insurance/credit-eligibility/");
    return {
      eligible: data.eligible,
      creditScore: data.credit_score,
      preapprovedLimit: Number(data.preapproved_limit),
      currency: data.currency,
      reasons: data.reasons,
      provider: data.provider,
    };
  },
};

export default partnerService;
