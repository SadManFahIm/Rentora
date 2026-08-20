import { api } from "./api";
import type { AddonOrder, AddonProvider, AddonService, MarketplaceRecommendation } from "../types";

// ============================================================
// MARKETPLACE SERVICE — add-on services + AI recommendations
// ============================================================

interface ApiAddonService {
  id: number;
  provider: number;
  provider_name: string;
  category: string;
  category_display: string;
  title: string;
  description: string;
  price: string | number;
  unit: string;
  is_active: boolean;
  rating_avg: string | number;
  rating_count: number;
  created_at: string;
}

interface ApiAddonOrder {
  id: number;
  service: number;
  service_title: string;
  provider_business: string;
  tenant: number;
  tenant_name: string;
  quantity: number;
  total: string | number;
  status: string;
  notes: string;
  created_at: string;
}

interface ApiAddonProvider {
  id: number;
  user: number;
  user_name: string;
  business_name: string;
  description: string;
  status: string;
  commission_rate: string | number | null;
  is_active: boolean;
  created_at: string;
}

export function mapAddonService(api: ApiAddonService): AddonService {
  return {
    id: api.id,
    provider: api.provider,
    providerName: api.provider_name,
    category: api.category as AddonService["category"],
    categoryDisplay: api.category_display,
    title: api.title,
    description: api.description,
    price: Number(api.price),
    unit: api.unit,
    isActive: api.is_active,
    ratingAvg: Number(api.rating_avg),
    ratingCount: api.rating_count,
    createdAt: api.created_at,
  };
}

function mapOrder(api: ApiAddonOrder): AddonOrder {
  return {
    id: api.id,
    service: api.service,
    serviceTitle: api.service_title,
    providerBusiness: api.provider_business,
    tenant: api.tenant,
    tenantName: api.tenant_name,
    quantity: api.quantity,
    total: Number(api.total),
    status: api.status as AddonOrder["status"],
    notes: api.notes,
    createdAt: api.created_at,
  };
}

function mapProvider(api: ApiAddonProvider): AddonProvider {
  return {
    id: api.id,
    user: api.user,
    userName: api.user_name,
    businessName: api.business_name,
    description: api.description,
    status: api.status as AddonProvider["status"],
    commissionRate: api.commission_rate != null ? Number(api.commission_rate) : null,
    isActive: api.is_active,
    createdAt: api.created_at,
  };
}

export const marketplaceService = {
  /** GET /marketplace/services/ — active add-on catalog. */
  async listServices(category?: string): Promise<AddonService[]> {
    const { data } = await api.get<ApiAddonService[]>("/marketplace/services/", {
      params: category ? { category } : {},
    });
    return data.map(mapAddonService);
  },

  /** GET /marketplace/services/:id/ */
  async getService(id: number): Promise<AddonService> {
    const { data } = await api.get<ApiAddonService>(`/marketplace/services/${id}/`);
    return mapAddonService(data);
  },

  /** GET /marketplace/orders/ — own orders. */
  async listOrders(): Promise<AddonOrder[]> {
    const { data } = await api.get<ApiAddonOrder[]>("/marketplace/orders/");
    return data.map(mapOrder);
  },

  /** POST /marketplace/orders/ */
  async createOrder(serviceId: number, quantity = 1, notes = ""): Promise<AddonOrder> {
    const { data } = await api.post<ApiAddonOrder>("/marketplace/orders/", {
      service_id: serviceId,
      quantity,
      notes,
    });
    return mapOrder(data);
  },

  /** POST /marketplace/orders/:id/action/ — confirm/cancel/complete. */
  async orderAction(id: number, action: "confirm" | "cancel" | "complete"): Promise<AddonOrder> {
    const { data } = await api.post<ApiAddonOrder>(`/marketplace/orders/${id}/action/`, {
      action,
    });
    return mapOrder(data);
  },

  /** GET /marketplace/recommendations/?booking_id= */
  async recommend(bookingId: number): Promise<MarketplaceRecommendation[]> {
    const { data } = await api.get<ApiRecommendation[]>("/marketplace/recommendations/", {
      params: { booking_id: bookingId },
    });
    return data.map((r) => ({
      bookingId: r.booking_id,
      services: r.services.map(mapAddonService),
      reasons: r.reasons,
    }));
  },

  /** GET /marketplace/provider/me/ — provider business profile. */
  async getProviderMe(): Promise<AddonProvider> {
    const { data } = await api.get<ApiAddonProvider>("/marketplace/provider/me/");
    return mapProvider(data);
  },

  /** POST /marketplace/provider/register/ */
  async registerProvider(input: {
    businessName: string;
    description: string;
  }): Promise<AddonProvider> {
    const { data } = await api.post<ApiAddonProvider>("/marketplace/provider/register/", {
      business_name: input.businessName,
      description: input.description,
    });
    return mapProvider(data);
  },
};

interface ApiRecommendation {
  booking_id: number;
  services: ApiAddonService[];
  reasons: Record<string, string>;
}

export default marketplaceService;
