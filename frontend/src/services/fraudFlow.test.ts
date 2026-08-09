/**
 * E2E-style client integration: the fraud x notification cycle the way the UI
 * drives it. The HTTP layer is mocked, but the REAL service, store, and badge
 * logic run end-to-end — mirroring backend/fraud/test_e2e.py step-for-step:
 *
 *   1. flag   → GET /fraud/rooms/{id}/status/ → badge label + unread notification
 *   2. re-scan → POST /fraud/rooms/{id}/scan/ → clean report → badge disappears
 *   3. admin review → POST /fraud/reports/{id}/review/ → status flips, unread
 *      notifications resolve via the store
 *
 * (Vitest runs in a node environment here — no DOM/component tests yet — so the
 * store + service boundary is the deepest integration point available.)
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./api", () => ({
  api: { get: vi.fn(), post: vi.fn() },
  isAuthenticated: vi.fn(() => true),
}));

vi.mock("./notificationService", () => ({
  notificationService: {
    getNotifications: vi.fn(),
    markAllRead: vi.fn(),
    markAsRead: vi.fn(),
  },
}));

import { api } from "./api";
import { notificationService } from "./notificationService";
import { fraudBadgeLabel } from "../lib/fraud";
import { fraudService } from "./fraudService";
import { useNotificationStore } from "../stores/notificationStore";
import type { Notification } from "../types";

const mockGet = api.get as ReturnType<typeof vi.fn>;
const mockPost = api.post as ReturnType<typeof vi.fn>;

// ---- fixtures (API wire shape) ----
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

const apiReport = {
  id: 4,
  room: apiRoom,
  severity: "high",
  severity_display: "High",
  status: "open",
  status_display: "Open",
  score: 100,
  summary: "Risk score 100/100. Signals: Duplicate Listing.",
  signals: [],
  created_at: "2025-01-05T10:00:00Z",
  updated_at: "2025-01-05T10:00:00Z",
};

const flaggedStatus = {
  room_id: 18,
  severity: "high",
  score: 100,
  flagged: true,
  message: "Risk score 100/100. Signals: Duplicate Listing.",
};

const cleanStatus = {
  room_id: 18,
  severity: "clean",
  score: 0,
  flagged: false,
  message: "No risk signals detected.",
};

const fraudNotification: Notification = {
  id: 99,
  text: "Your listing 'Modern Studio, Mirpur' was flagged by our fraud detection (high risk).",
  read: false,
  time: "2025-01-05T10:00:00Z",
};

describe("fraud x notification flow (client E2E)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useNotificationStore.setState({ notifications: [], unreadCount: 0, loading: false });
  });

  it("flag → badge + unread notification → re-scan clears both", async () => {
    // 1. Landlord opens the room modal → GET status → flagged HIGH.
    mockGet.mockResolvedValueOnce({ data: flaggedStatus });
    const status = await fraudService.getRoomStatus(18);
    expect(status.flagged).toBe(true);
    expect(status.score).toBe(100);
    // The exact string the RoomModal badge renders for a HIGH flag.
    expect(fraudBadgeLabel(status.severity)).toBe("Under review (high risk)");

    // 2. The WebSocket push lands the fraud_flag notification → unread 1.
    useNotificationStore.getState().addNotification(fraudNotification);
    expect(useNotificationStore.getState().unreadCount).toBe(1);
    expect(useNotificationStore.getState().notifications[0].read).toBe(false);

    // 3. Landlord fixes the listing and re-scans → report comes back clean.
    mockPost.mockResolvedValueOnce({
      data: { ...apiReport, severity: "clean", score: 0 },
    });
    const report = await fraudService.scanRoom(18);
    expect(mockPost).toHaveBeenCalledWith("/fraud/rooms/18/scan/");
    expect(report.severity).toBe("clean");
    expect(report.score).toBe(0);

    // 4. Public status flips → the badge disappears.
    mockGet.mockResolvedValueOnce({ data: cleanStatus });
    const after = await fraudService.getRoomStatus(18);
    expect(after.flagged).toBe(false);
    // Clean severity never carries a badge label.
    expect(fraudBadgeLabel(after.severity)).toBe("");
    // …whereas an informational low-severity flag still shows the bare badge.
    expect(fraudBadgeLabel("low")).toBe("Under review");
  });

  it("admin review flow: list → review → status reviewed + notifications resolved", async () => {
    // 1. Admin opens the reports dashboard (filtered to open reports).
    mockGet.mockResolvedValueOnce({ data: [apiReport] });
    const reports = await fraudService.getReports({ status: "open" });
    expect(mockGet).toHaveBeenCalledWith("/fraud/reports/", {
      params: { status: "open" },
    });
    expect(reports).toHaveLength(1);
    expect(reports[0].severity).toBe("high");
    expect(reports[0].status).toBe("open");

    // 2. Admin marks the report reviewed.
    mockPost.mockResolvedValueOnce({
      data: { ...apiReport, status: "reviewed", status_display: "Reviewed" },
    });
    const reviewed = await fraudService.reviewReport(4, "reviewed");
    expect(mockPost).toHaveBeenCalledWith("/fraud/reports/4/review/", {
      action: "reviewed",
    });
    expect(reviewed.status).toBe("reviewed");
    expect(reviewed.statusDisplay).toBe("Reviewed");

    // 3. The flag notification is still unread for the landlord… then resolved.
    useNotificationStore.getState().addNotification(fraudNotification);
    expect(useNotificationStore.getState().unreadCount).toBe(1);

    await useNotificationStore.getState().markAllRead();
    expect(useNotificationStore.getState().unreadCount).toBe(0);
    expect(notificationService.markAllRead).toHaveBeenCalledOnce();
  });

  it("rejected re-scan keeps the badge until the listing is fixed", async () => {
    // A re-scan that still finds the duplicate must keep the flag visible.
    mockPost.mockResolvedValueOnce({ data: apiReport }); // still high/open
    const report = await fraudService.scanRoom(18);
    expect(report.severity).toBe("high");
    expect(fraudBadgeLabel(report.severity)).toBe("Under review (high risk)");
  });
});
