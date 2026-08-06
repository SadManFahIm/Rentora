import { describe, expect, it, vi, beforeEach } from "vitest";
import { mapSignal, mapReport } from "./fraudService";

vi.mock("./api", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

import { api } from "./api";
import { fraudService } from "./fraudService";

const apiRoom = {
  id: 18,
  title: "Modern Studio, Mirpur",
  description: "Bright studio.",
  room_type: "studio",
  price: "13500.00",
  area: "Mirpur",
  lat: "23.81",
  lng: "90.37",
  amenities: ["wifi"],
  gender_preference: "any",
  size_sqft: 420,
  is_available: true,
  is_featured: false,
  rating: "4.6",
  total_reviews: 15,
  verified: false,
  created_at: "2025-01-01T00:00:00Z",
};

const apiSignal = {
  id: 1,
  detector: "duplicate_listing",
  detector_display: "Duplicate Listing",
  severity: "high",
  message: "Title is 100% similar to listing #7.",
  detail: { similar_room_id: 7, similarity: 1.0 },
  created_at: "2025-01-05T10:00:00Z",
};

const apiReport = {
  id: 4,
  room: apiRoom,
  severity: "high",
  severity_display: "High",
  status: "open",
  status_display: "Open",
  score: 100,
  summary: "Risk score 100/100. Signals: Duplicate Listing.",
  signals: [apiSignal],
  created_at: "2025-01-05T10:00:00Z",
  updated_at: "2025-01-05T10:00:00Z",
};

describe("mapSignal", () => {
  it("maps detector display and detail", () => {
    const s = mapSignal(apiSignal);
    expect(s).toMatchObject({
      id: 1,
      detector: "duplicate_listing",
      detectorDisplay: "Duplicate Listing",
      severity: "high",
      detail: { similar_room_id: 7, similarity: 1.0 },
    });
  });
});

describe("mapReport", () => {
  it("maps report and nests the room + signals", () => {
    const r = mapReport(apiReport);
    expect(r).toMatchObject({
      id: 4,
      severity: "high",
      severityDisplay: "High",
      status: "open",
      statusDisplay: "Open",
      score: 100,
      summary: "Risk score 100/100. Signals: Duplicate Listing.",
    });
    expect(r.room.name).toBe("Modern Studio, Mirpur");
    expect(r.signals).toHaveLength(1);
    expect(r.signals[0].detectorDisplay).toBe("Duplicate Listing");
  });
});

describe("fraudService", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("getRoomStatus maps snake_case to camelCase", async () => {
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: {
        room_id: 18,
        severity: "high",
        score: 100,
        flagged: true,
        message: "Risk signals detected.",
      },
    });
    const status = await fraudService.getRoomStatus(18);
    expect(status).toMatchObject({
      roomId: 18,
      severity: "high",
      score: 100,
      flagged: true,
    });
    expect(api.get).toHaveBeenCalledWith("/fraud/rooms/18/status/");
  });

  it("getReports passes filter params through", async () => {
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: [apiReport],
    });
    await fraudService.getReports({ status: "open", severity: "high" });
    expect(api.get).toHaveBeenCalledWith("/fraud/reports/", {
      params: { status: "open", severity: "high" },
    });
  });

  it("scanRoom posts to the right endpoint", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: apiReport,
    });
    const report = await fraudService.scanRoom(18);
    expect(api.post).toHaveBeenCalledWith("/fraud/rooms/18/scan/");
    expect(report.score).toBe(100);
  });

  it("reviewReport posts action", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { ...apiReport, status: "reviewed" },
    });
    await fraudService.reviewReport(4, "reviewed");
    expect(api.post).toHaveBeenCalledWith("/fraud/reports/4/review/", {
      action: "reviewed",
    });
  });
});
