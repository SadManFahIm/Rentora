import { api } from "./api";
import { mapNotification, type ApiNotification, type Paginated } from "./mappers";
import type { Notification } from "../types";

// ============================================================
// NOTIFICATION SERVICE — real /notifications/ endpoints
// ============================================================

export const notificationService = {
  /** GET /notifications/ → the user's notifications (first page). */
  async getNotifications(): Promise<Notification[]> {
    const { data } = await api.get<Paginated<ApiNotification>>("/notifications/");
    return data.results.map(mapNotification);
  },

  /** PATCH /notifications/:id/ → mark a single notification read. */
  async markAsRead(id: number): Promise<Notification> {
    const { data } = await api.patch<ApiNotification>(`/notifications/${id}/`, {
      is_read: true,
    });
    return mapNotification(data);
  },

  /** POST /notifications/mark-all-read/ → returns how many were flipped. */
  async markAllRead(): Promise<number> {
    const { data } = await api.post<{ marked_count: number }>(
      "/notifications/mark-all-read/"
    );
    return data.marked_count;
  },

  /** GET /notifications/unread-count/ */
  async getUnreadCount(): Promise<number> {
    const { data } = await api.get<{ count: number }>(
      "/notifications/unread-count/"
    );
    return data.count;
  },
};

export default notificationService;
