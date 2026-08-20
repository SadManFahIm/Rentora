import { describe, expect, it, vi, beforeEach } from "vitest";

vi.mock("./api", () => ({
  api: {
    post: vi.fn(),
    get: vi.fn(),
    patch: vi.fn(),
  },
  default: {
    post: vi.fn(),
    get: vi.fn(),
    patch: vi.fn(),
  },
}));

vi.mock("./mappers", () => ({
  mapRoom: (r: unknown) => ({ ...(r as object), img: "/img.jpg" }),
}));

import { api } from "./api";
import visionService from "./visionService";

const analysisPayload = {
  available: true,
  provider: "heuristic",
  caption: "A bright, airy single room with a calm light-tone palette.",
  observations: [
    { kind: "lighting", label: "Well-lit space", confidence: 0.9 },
    { kind: "tone", label: "Light-tone interiors", confidence: 0.8 },
  ],
  suggested_amenities: [],
  palette: [{ hex: "#f2f0e8", name: "Ivory", share: 0.34 }],
  photo_count: 1,
  note: "Photo intelligence is statistical.",
};

const matchPayload = {
  matches: [
    {
      id: 1,
      title: "Student Room, Uttara",
      price: 8500,
      area: "Uttara",
      room_type: "single",
      amenities: ["WiFi"],
      verified: true,
      tier: "free",
      image: null,
      match_score: 88,
      reasons: ["Similar composition", "Bright and airy"],
    },
  ],
  note: "Visual similarity, not object recognition.",
};

describe("visionService", () => {
  beforeEach(() => vi.clearAllMocks());

  it("analyzes a room's photos", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: analysisPayload });
    const res = await visionService.analyzeRoom(7);
    expect(res.available).toBe(true);
    expect(res.caption).toContain("bright");
    expect(res.palette[0].name).toBe("Ivory");
    expect(api.post).toHaveBeenCalledWith("/rooms/7/vision/analyze/");
  });

  it("fetches a stored analysis", async () => {
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: analysisPayload });
    const res = await visionService.getVision(7);
    expect(res.provider).toBe("heuristic");
    expect(res.observations).toHaveLength(2);
    expect(api.get).toHaveBeenCalledWith("/rooms/7/vision/");
  });

  it("requests an AI draft from the listing photos", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { title: "Bright Room", description: "…", amenities: [], observations: [], note: "" },
    });
    const res = await visionService.getVisionDescription(7);
    expect(res.title).toBe("Bright Room");
    expect(api.post).toHaveBeenCalledWith("/rooms/7/vision/description/");
  });

  it("uploads an image and maps matches", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: matchPayload });
    const file = new File(["x"], "room.png", { type: "image/png" });
    const res = await visionService.searchByImage(file);
    expect(res.matches).toHaveLength(1);
    expect(res.matches[0].match_score).toBe(88);
    expect(res.matches[0].reasons).toContain("Similar composition");
    expect(api.post).toHaveBeenCalledWith(
      "/rooms/vision/search/",
      expect.any(FormData),
      expect.objectContaining({ headers: { "Content-Type": undefined } })
    );
  });

  it("returns an empty match list when nothing looks alike", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { matches: [], note: "No close visual matches." },
    });
    const file = new File(["y"], "other.png", { type: "image/png" });
    const res = await visionService.searchByImage(file);
    expect(res.matches).toEqual([]);
  });
});
