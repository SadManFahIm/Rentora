import { create } from "zustand";
import { mockNotifications } from "../data/mockData";
import type { Notification } from "../types";

// ============================================================
// NOTIFICATION STORE — in-app notifications
// Seeded with mock data; replaced by API data in Phase 3.
// ============================================================

interface NotificationState {
  notifications: Notification[];
  unreadCount: () => number;
  setNotifications: (notifications: Notification[]) => void;
  addNotification: (notification: Notification) => void;
  markAllRead: () => void;
  markRead: (id: number) => void;
}

export const useNotificationStore = create<NotificationState>()((set, get) => ({
  notifications: mockNotifications,
  unreadCount: () => get().notifications.filter((n) => !n.read).length,
  setNotifications: (notifications) => set({ notifications }),
  addNotification: (notification) =>
    set((s) => ({ notifications: [notification, ...s.notifications] })),
  markAllRead: () =>
    set((s) => ({
      notifications: s.notifications.map((n) => ({ ...n, read: true })),
    })),
  markRead: (id) =>
    set((s) => ({
      notifications: s.notifications.map((n) =>
        n.id === id ? { ...n, read: true } : n
      ),
    })),
}));
