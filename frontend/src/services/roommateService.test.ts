import { describe, expect, it, vi, beforeEach } from "vitest";
import { mapProfile, mapMatch, mapRequest } from "./roommateService";
import type { RoommateProfilePayload } from "../types";

// Mock the shared API client so service tests never touch the network.
vi.mock("./api", () => ({
  api: {
    get: vi.fn(),
    put: vi.fn(),
    post: vi.fn(),
  },
}));

// Load the mocked module *after* the mock is registered.
import { api } from "./api";
import { roommateService } from "./roommateService";

const apiProfile = {
  id: 5,
  username: "sabbir.rahman",
  budget_min: "6000.00",
  budget_max: "11000.00",
  preferred_area: "Mirpur",
  room_type_pref: "shared",
  gender_pref: "any",
  lifestyle: ["non_smoker", "quiet"],
  occupation: "Banker",
  bio: "Mostly away on weekdays.",
  move_in_date: null,
  is_looking: true,
  created_at: "2025-01-01T10:00:00Z",
  updated_at: "2025-01-02T10:00:00Z",
};

const apiUser = {
  id: 5,
  username: "sabbir.rahman",
  first_name: "Sabbir",
  last_name: "Rahman",
  avatar: null,
  phone: "",
  nid_verified: true,
};

const apiMatch = {
  score: 87,
  reasons: ["Budgets overlap well", "Same preferred area"],
  profile: { ...apiProfile, user: apiUser },
};

describe("mapProfile", () => {
  it("converts snake_case API fields to camelCase", () => {
    const p = mapProfile(apiProfile);
    expect(p).toMatchObject({
      id: 5,
      username: "sabbir.rahman",
      budgetMin: 6000,
      budgetMax: 11000,
      preferredArea: "Mirpur",
      roomTypePref: "shared",
      genderPref: "any",
      lifestyle: ["non_smoker", "quiet"],
      isLooking: true,
    });
  });

  it("parses decimal strings into numbers", () => {
    const p = mapProfile(apiProfile);
    expect(p.budgetMin).toBe(6000);
    expect(p.budgetMax).toBe(11000);
  });
});

describe("mapMatch", () => {
  it("keeps score and reasons and attaches the nested user", () => {
    const m = mapMatch(apiMatch);
    expect(m.score).toBe(87);
    expect(m.reasons).toEqual(["Budgets overlap well", "Same preferred area"]);
    expect(m.profile.username).toBe("sabbir.rahman");
    expect(m.profile.user).toBeDefined();
  });
});

describe("mapRequest", () => {
  it("maps a request with direction and status display", () => {
    const apiReq = {
      id: 3,
      sender: { ...apiUser, id: 2, username: "rahim.hossain" },
      receiver: apiUser,
      message: "Let's share!",
      status: "pending",
      status_display: "Pending",
      direction: "outgoing",
      created_at: "2025-01-03T09:00:00Z",
      updated_at: "2025-01-03T09:00:00Z",
    };
    const r = mapRequest(apiReq);
    expect(r).toMatchObject({
      id: 3,
      message: "Let's share!",
      status: "pending",
      statusDisplay: "Pending",
      direction: "outgoing",
    });
  });
});

describe("roommateService", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("getMyProfile returns null on 404 (no profile yet)", async () => {
    (api.get as ReturnType<typeof vi.fn>).mockRejectedValueOnce({
      response: { status: 404 },
    });
    await expect(roommateService.getMyProfile()).resolves.toBeNull();
  });

  it("getMyProfile rethrows non-404 errors", async () => {
    (api.get as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error("boom"));
    await expect(roommateService.getMyProfile()).rejects.toThrow("boom");
  });

  it("saveMyProfile sends snake_case payload", async () => {
    (api.put as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: apiProfile,
    });
    const payload: RoommateProfilePayload = {
      budgetMin: 6000,
      budgetMax: 11000,
      preferredArea: "Mirpur",
      roomTypePref: "shared",
      genderPref: "any",
      lifestyle: ["non_smoker"],
      occupation: "Banker",
      bio: "",
      moveInDate: null,
      isLooking: true,
    };
    await roommateService.saveMyProfile(payload);
    expect(api.put).toHaveBeenCalledWith("/roommates/profile/", {
      budget_min: 6000,
      budget_max: 11000,
      preferred_area: "Mirpur",
      room_type_pref: "shared",
      gender_pref: "any",
      lifestyle: ["non_smoker"],
      occupation: "Banker",
      bio: "",
      move_in_date: null,
      is_looking: true,
    });
  });

  it("getMatches maps every match", async () => {
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: [apiMatch, { ...apiMatch, score: 76 }],
    });
    const matches = await roommateService.getMatches();
    expect(matches).toHaveLength(2);
    expect(matches[0].score).toBe(87);
    expect(matches[1].score).toBe(76);
  });

  it("sendRequest posts receiver_id and message", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: {
        id: 9,
        sender: { ...apiUser, id: 2, username: "rahim.hossain" },
        receiver: apiUser,
        message: "hi",
        status: "pending",
        status_display: "Pending",
        direction: "outgoing",
        created_at: "2025-01-04T00:00:00Z",
        updated_at: "2025-01-04T00:00:00Z",
      },
    });
    await roommateService.sendRequest(5, "hi");
    expect(api.post).toHaveBeenCalledWith("/roommates/requests/", {
      receiver_id: 5,
      message: "hi",
    });
  });

  it("respondToRequest posts the action to the right endpoint", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: {
        id: 9,
        sender: { ...apiUser, id: 2, username: "rahim.hossain" },
        receiver: apiUser,
        message: "hi",
        status: "approved",
        status_display: "Approved",
        direction: "incoming",
        created_at: "2025-01-04T00:00:00Z",
        updated_at: "2025-01-04T00:00:00Z",
      },
    });
    await roommateService.respondToRequest(9, "approve");
    expect(api.post).toHaveBeenCalledWith("/roommates/requests/9/action/", {
      action: "approve",
    });
  });
});
