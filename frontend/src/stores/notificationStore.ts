import { create } from "zustand";
import { isAuthenticated } from "../services/api";
import { notificationService } from "../services/notificationService";
import type { Notification } from "../types";

// ============================================================
// NOTIFICATION STORE — backed by the /notifications/ API.
// ============================================================

interface NotificationState {
  notifications: Notification[];
  unreadCount: number;
  loading: boolean;
  /** Fetch the latest notifications + unread count from the backend. */
  fetch: () => Promise<void>;
  /** Mark every unread notification read (server + local). */
  markAllRead: () => Promise<void>;
  /** Mark a single notification read (server + local). */
  markRead: (id: number) => Promise<void>;
  clear: () => void;
}

const countUnread = (items: Notification[]): number =>
  items.filter((n) => !n.read).length;

export const useNotificationStore = create<NotificationState>()((set, get) => ({
  notifications: [],
  unreadCount: 0,
  loading: false,

  fetch: async () => {
    if (!isAuthenticated()) {
      set({ notifications: [], unreadCount: 0 });
      return;
    }
    set({ loading: true });
    try {
      const notifications = await notificationService.getNotifications();
      set({ notifications, unreadCount: countUnread(notifications) });
    } catch {
      // Non-fatal — leave existing state in place.
    } finally {
      set({ loading: false });
    }
  },

  markAllRead: async () => {
    const previous = get().notifications;
    // Optimistic.
    set({
      notifications: previous.map((n) => ({ ...n, read: true })),
      unreadCount: 0,
    });
    try {
      await notificationService.markAllRead();
    } catch {
      set({ notifications: previous, unreadCount: countUnread(previous) });
    }
  },

  markRead: async (id) => {
    const previous = get().notifications;
    const next = previous.map((n) => (n.id === id ? { ...n, read: true } : n));
    set({ notifications: next, unreadCount: countUnread(next) });
    try {
      await notificationService.markAsRead(id);
    } catch {
      set({ notifications: previous, unreadCount: countUnread(previous) });
    }
  },

  clear: () => set({ notifications: [], unreadCount: 0 }),
}));
