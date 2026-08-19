/**
 * Component test for the Phase 15 — C6 rental market report card: renders
 * the public digest (highlights, area table, WoW movement) and the admin
 * generate action. The service is mocked; rendering + wiring are under test.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import MarketReportCard from "./MarketReportCard";

vi.mock("../../services/marketReportService", () => ({
  default: {
    get: vi.fn(),
    generate: vi.fn(),
  },
}));

import marketReportService from "../../services/marketReportService";

const mockGet = marketReportService.get as ReturnType<typeof vi.fn>;
const mockGenerate = marketReportService.generate as ReturnType<typeof vi.fn>;

function renderCard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MarketReportCard />
    </QueryClientProvider>
  );
}

const report = {
  week_label: "Week 33 — Aug 17–23, 2026",
  as_of: "2026-08-19T06:00:00Z",
  areas: [
    {
      area: "Uttara",
      avg_price: 12000,
      median_price: 11500,
      sample_size: 42,
      available_count: 18,
      total_count: 60,
      availability_pct: 30,
      demand_index: 78,
      direction: "rising",
      forecast_30d: 12,
      prev_avg_price: 11800,
      price_change_pct: 1.7,
    },
    {
      area: "Mirpur",
      avg_price: 9000,
      median_price: 8800,
      sample_size: 35,
      available_count: 10,
      total_count: 45,
      availability_pct: 22,
      demand_index: 45,
      direction: "falling",
      forecast_30d: 3,
      prev_avg_price: 9200,
      price_change_pct: -2.2,
    },
  ],
  rising: ["Uttara"],
  falling: ["Mirpur"],
  highlights: [
    {
      area: "Uttara",
      kind: "rising",
      text: "Demand in Uttara is rising (index 78/100, 30-day forecast +12 signals).",
    },
  ],
  summary_bn: "সামগ্রিক চিত্র…",
  baseline: false,
  note: "Automatic report from live MarketStat prices.",
};

describe("MarketReportCard (Phase 15 — C6)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGet.mockResolvedValue(report);
    mockGenerate.mockResolvedValue({ week_label: "Week 33", areas: 2, baseline: false });
  });

  it("renders the digest: week label, highlights and area rows", async () => {
    renderCard();
    expect(await screen.findByText("Week 33 — Aug 17–23, 2026")).toBeInTheDocument();
    expect(screen.getByText(/Demand in Uttara is rising/)).toBeInTheDocument();
    expect(screen.getByText("Uttara")).toBeInTheDocument();
    expect(screen.getByText("12,000")).toBeInTheDocument();
    expect(screen.getByText("rising · 78")).toBeInTheDocument();
    expect(screen.getByText("+1.7%")).toBeInTheDocument();
    expect(screen.getByText("-2.2%")).toBeInTheDocument();
  });

  it("shows the baseline note on the first snapshot", async () => {
    mockGet.mockResolvedValue({ ...report, baseline: true });
    renderCard();
    expect(await screen.findByText(/baseline week/)).toBeInTheDocument();
  });

  it("generates the report on the admin action", async () => {
    const user = userEvent.setup();
    renderCard();
    await user.click(await screen.findByRole("button", { name: /generate & email landlords/i }));
    expect(mockGenerate).toHaveBeenCalledTimes(1);
    expect(await screen.findByText(/Snapshot written for Week 33/)).toBeInTheDocument();
  });

  it("recovers from a load error via retry", async () => {
    mockGet.mockRejectedValueOnce(new Error("down"));
    renderCard();
    expect(await screen.findByText(/Could not load the market report/)).toBeInTheDocument();
    mockGet.mockResolvedValue(report);
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(await screen.findByText("Week 33 — Aug 17–23, 2026")).toBeInTheDocument();
  });
});
