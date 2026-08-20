import { describe, expect, it, vi, beforeEach } from "vitest";

vi.mock("./api", () => ({
  api: { get: vi.fn(), post: vi.fn() },
}));

import { api } from "./api";
import { corporateService } from "./corporateService";
import { marketplaceService } from "./marketplaceService";
import { partnerService } from "./partnerService";

describe("corporateService", () => {
  beforeEach(() => vi.clearAllMocks());

  it("bulkBooking posts room/members/dates", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { succeeded: 2, failed: 1 },
    });
    const r = await corporateService.bulkBooking({
      roomId: 11,
      memberIds: [1, 2, 3],
      dateFrom: "2025-02-01",
      dateTo: "2025-02-28",
    });
    expect(api.post).toHaveBeenCalledWith("/corporate/bulk-booking/", {
      room_id: 11,
      member_ids: [1, 2, 3],
      date_from: "2025-02-01",
      date_to: "2025-02-28",
    });
    expect(r.succeeded).toBe(2);
  });

  it("createAccount maps vat_number to camelCase", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: {
        id: 1,
        name: "ACME Ltd",
        email: "hr@acme.com",
        phone: "01700000000",
        address: "Uttara",
        vat_number: "VAT-1",
        owner: 9,
        owner_name: "Rahim Hossain",
        status: "active",
        created_at: "2025-01-01T00:00:00Z",
      },
    });
    const acc = await corporateService.createAccount({
      name: "ACME Ltd",
      email: "hr@acme.com",
      phone: "01700000000",
      address: "Uttara",
    });
    expect(acc.vatNumber).toBe("VAT-1");
    expect(acc.status).toBe("active");
  });
});

describe("marketplaceService", () => {
  beforeEach(() => vi.clearAllMocks());

  it("createOrder posts service_id and maps totals", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: {
        id: 1,
        service: 5,
        service_title: "Deep Clean",
        provider_business: "Sparkle Co",
        tenant: 9,
        tenant_name: "Rahim Hossain",
        quantity: 2,
        total: "600",
        status: "pending",
        notes: "",
        created_at: "2025-01-01T00:00:00Z",
      },
    });
    const order = await marketplaceService.createOrder(5, 2, "");
    expect(api.post).toHaveBeenCalledWith("/marketplace/orders/", {
      service_id: 5,
      quantity: 2,
      notes: "",
    });
    expect(order.total).toBe(600);
    expect(order.serviceTitle).toBe("Deep Clean");
  });

  it("recommend passes booking_id param", async () => {
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: [] });
    await marketplaceService.recommend(42);
    expect(api.get).toHaveBeenCalledWith("/marketplace/recommendations/", {
      params: { booking_id: 42 },
    });
  });
});

describe("partnerService", () => {
  beforeEach(() => vi.clearAllMocks());

  it("createQuote posts product + coverage and maps status display", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: {
        id: 1,
        product: {
          id: 1,
          partner: 2,
          partner_name: "Guardian",
          code: "RENT-PRO",
          name: "Rent Protect",
          coverage: { rent: true, fire: true },
          price_monthly: "150",
          deductible: "1000",
          is_active: true,
        },
        price: "1800",
        coverage_period: 12,
        status: "quoted",
        status_display: "Quoted",
        quote_data: {},
        created_at: "2025-01-01T00:00:00Z",
      },
    });
    const quote = await partnerService.createQuote(1, 12);
    expect(api.post).toHaveBeenCalledWith("/partner-services/insurance/quotes/", {
      product_id: 1,
      coverage_period: 12,
    });
    expect(quote.price).toBe(1800);
    expect(quote.product.name).toBe("Rent Protect");
  });

  it("creditEligibility maps preapproved_limit", async () => {
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: {
        eligible: true,
        credit_score: 720,
        preapproved_limit: "50000",
        currency: "BDT",
        reasons: ["good score"],
        provider: "rule",
      },
    });
    const credit = await partnerService.creditEligibility();
    expect(credit.preapprovedLimit).toBe(50000);
    expect(credit.eligible).toBe(true);
  });
});
