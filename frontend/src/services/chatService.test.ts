import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./api", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

import { api } from "./api";
import { chatService } from "./chatService";

const apiReport = {
  id: 31,
  reporter_username: "nadia.islam",
  reporter_name: "Nadia Islam",
  target_user: 5,
  target_username: "sabbir.rahman",
  target_name: "Sabbir Rahman",
  message: 88,
  category: "payment_fraud",
  category_display: "Payment fraud",
  description: "Asked me to send rent outside the app.",
  status: "open",
  status_display: "Open",
  action_taken: "",
  action_taken_display: "—",
  admin_note: "",
  created_at: "2025-01-05T10:00:00Z",
  resolved_at: null,
};

describe("chatService report/block (Phase 12.4)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("reportUser posts target, category, description and message anchor", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: apiReport });
    const report = await chatService.reportUser({
      targetUserId: 5,
      category: "payment_fraud",
      description: "Asked me to send rent outside the app.",
      messageId: 88,
    });
    expect(api.post).toHaveBeenCalledWith("/chat/reports/", {
      target_user_id: 5,
      category: "payment_fraud",
      description: "Asked me to send rent outside the app.",
      message_id: 88,
    });
    expect(report.categoryDisplay).toBe("Payment fraud");
    expect(report.messageId).toBe(88);
  });

  it("reportUser defaults message_id to null when reporting the user only", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { ...apiReport, message: null },
    });
    await chatService.reportUser({ targetUserId: 5, category: "harassment" });
    expect(api.post).toHaveBeenCalledWith("/chat/reports/", {
      target_user_id: 5,
      category: "harassment",
      description: "",
      message_id: null,
    });
  });

  it("blockUser posts the user_id", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: {} });
    await chatService.blockUser(5);
    expect(api.post).toHaveBeenCalledWith("/chat/block/", { user_id: 5 });
  });

  it("unblockUser deletes the block", async () => {
    (api.delete as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: {} });
    await chatService.unblockUser(5);
    expect(api.delete).toHaveBeenCalledWith("/chat/block/5/");
  });

  it("getBlockedUsers lists the caller's blocks", async () => {
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: [{ id: 5, username: "sabbir.rahman" }],
    });
    const blocked = await chatService.getBlockedUsers();
    expect(api.get).toHaveBeenCalledWith("/chat/blocked/");
    expect(blocked).toEqual([{ id: 5, username: "sabbir.rahman" }]);
  });

  it("getReports passes the status filter (and omits it for all)", async () => {
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: [apiReport] });
    await chatService.getReports("open");
    expect(api.get).toHaveBeenCalledWith("/chat/reports/admin/", { params: { status: "open" } });

    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: [apiReport] });
    await chatService.getReports("all");
    expect(api.get).toHaveBeenCalledWith("/chat/reports/admin/", { params: undefined });
  });

  it("actOnReport posts the admin decision with the note", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { ...apiReport, status: "resolved", status_display: "Resolved", action_taken: "warn" },
    });
    const report = await chatService.actOnReport(31, "warn", "Please stop sharing payment links.");
    expect(api.post).toHaveBeenCalledWith("/chat/reports/31/action/", {
      action: "warn",
      note: "Please stop sharing payment links.",
    });
    expect(report.status).toBe("resolved");
    expect(report.actionTaken).toBe("warn");
  });
});
