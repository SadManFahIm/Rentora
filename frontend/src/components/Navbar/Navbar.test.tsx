/**
 * Navbar notification bell: unread-count badge + "Mark all read".
 * The zustand notification store runs for real (seeded via setState) while
 * its HTTP dependency is mocked — same depth as services/fraudFlow.test.ts.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Notification } from "../../types";
import Navbar from "./Navbar";

vi.mock("react-router-dom", () => ({
  NavLink: ({ children, to }: { children: React.ReactNode; to: string }) => (
    <a href={to}>{children}</a>
  ),
  useNavigate: () => vi.fn(),
}));

vi.mock("sonner", () => ({
  toast: vi.fn(),
}));

vi.mock("../../context/AppContext", () => ({
  useApp: () => ({ user: null }),
}));

vi.mock("../../stores/uiStore", () => ({
  useUiStore: () => ({ darkMode: false, toggleDarkMode: vi.fn() }),
}));

vi.mock("../../stores/wishlistStore", () => ({
  useWishlistStore: () => ({ wishlist: [] }),
}));

vi.mock("../../hooks/useAuth", () => ({
  useLogout: () => ({ mutate: vi.fn() }),
}));

vi.mock("../../hooks/useWebSocket", () => ({
  useWebSocket: () => ({ lastMessage: null }),
}));

vi.mock("../../services/mappers", () => ({
  mapNotification: vi.fn(),
}));

vi.mock("../../services/api", () => ({
  isAuthenticated: vi.fn(() => false),
}));

vi.mock("../../services/notificationService", () => ({
  notificationService: {
    getNotifications: vi.fn(),
    markAllRead: vi.fn(),
    markAsRead: vi.fn(),
  },
}));

import { notificationService } from "../../services/notificationService";
import { useNotificationStore } from "../../stores/notificationStore";

const notification = (id: number, read: boolean): Notification => ({
  id,
  text: `Notification ${id}`,
  read,
  time: "2025-01-05T10:00:00Z",
});

function seedStore(...items: Notification[]) {
  useNotificationStore.setState({
    notifications: items,
    unreadCount: items.filter((n) => !n.read).length,
  });
}

function clickBell() {
  const bell = screen.getAllByRole("button").find((b) => b.querySelector(".lucide-bell"))!;
  return userEvent.click(bell);
}

describe("Navbar notification bell", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useNotificationStore.setState({ notifications: [], unreadCount: 0 });
  });

  it("shows an unread-count badge on the bell", () => {
    seedStore(notification(1, false), notification(2, false), notification(3, true));
    render(<Navbar />);

    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("hides the badge when everything is read", () => {
    seedStore(notification(1, true), notification(2, true));
    render(<Navbar />);

    expect(screen.queryByText("2")).not.toBeInTheDocument();
    expect(screen.queryByText("1")).not.toBeInTheDocument();
  });

  it("opens the panel, lists notifications, and mark-all-read clears the badge", async () => {
    const user = userEvent.setup();
    seedStore(notification(1, false), notification(2, false));
    render(<Navbar />);

    // Open the dropdown.
    await clickBell();
    expect(screen.getAllByText("Notifications").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Notification 1").length).toBeGreaterThan(0);

    // Mark all read -> server call + badge disappears.
    await user.click(screen.getAllByText("Mark all read")[0]);
    expect(notificationService.markAllRead).toHaveBeenCalledOnce();

    await waitFor(() => {
      expect(screen.queryByText("2")).not.toBeInTheDocument();
    });
    expect(useNotificationStore.getState().notifications.every((n) => n.read)).toBe(true);
  });
});
