import { useEffect, useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Menu, X, Sun, Moon, Heart, Bell, ChevronDown, Building2 } from "lucide-react";
import { useApp } from "../../context/AppContext";
import { useUiStore } from "../../stores/uiStore";
import { useWishlistStore } from "../../stores/wishlistStore";
import { useNotificationStore } from "../../stores/notificationStore";
import { useLogout } from "../../hooks/useAuth";
import { useWebSocket } from "../../hooks/useWebSocket";
import { AREAS_INFO } from "../../data/areas";
import { mapNotification, type ApiNotification } from "../../services/mappers";
import tier4Service, { type SmartAlert } from "../../services/tier4Service";
import { Button } from "../ui/button";
import { Badge } from "../ui/badge";
import PwaInstallPrompt from "../PwaInstallPrompt/PwaInstallPrompt";
import BangladeshFlag from "../BangladeshFlag/BangladeshFlag";
import LanguageToggle from "../LanguageToggle/LanguageToggle";
import { cn } from "../../lib/utils";

interface NotificationWsEvent {
  type: "notification";
  data: ApiNotification;
}

const NAV_KEYS: { key: string; to: string }[] = [
  { key: "nav.home", to: "/" },
  { key: "nav.rooms", to: "/rooms" },
  { key: "nav.map", to: "/map" },
  { key: "nav.chat", to: "/chat" },
  { key: "nav.roommates", to: "/roommates" },
  { key: "nav.services", to: "/services" },
];

export default function Navbar() {
  const { user } = useApp();
  const darkMode = useUiStore((s) => s.darkMode);
  const toggleDarkMode = useUiStore((s) => s.toggleDarkMode);
  const wishlist = useWishlistStore((s) => s.wishlist);
  const notifications = useNotificationStore((s) => s.notifications);
  const markAllRead = useNotificationStore((s) => s.markAllRead);
  const logout = useLogout();
  const { t } = useTranslation();

  const [showNotif, setShowNotif] = useState(false);
  const [areasOpen, setAreasOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [smartAlerts, setSmartAlerts] = useState<SmartAlert[]>([]);
  const navigate = useNavigate();
  const unreadCount = notifications.filter((n) => !n.read).length;

  // Live notification push. `enabled` (tied to `user`) means this connects on
  // login and the hook's own cleanup disconnects it on logout.
  const { lastMessage: notificationEvent } = useWebSocket<NotificationWsEvent>(
    "/ws/notifications/",
    { enabled: !!user }
  );

  // Tier 4 Smart AI Alerts: when the dropdown opens, fetch the priority-
  // ranked feed so the top alert can be surfaced above the plain list.
  useEffect(() => {
    if (!showNotif || !user) return;
    let cancelled = false;
    tier4Service
      .smartAlerts()
      .then((alerts) => {
        if (!cancelled) setSmartAlerts(alerts);
      })
      .catch(() => {
        if (!cancelled) setSmartAlerts([]);
      });
    return () => {
      cancelled = true;
    };
  }, [showNotif, user]);

  useEffect(() => {
    if (!notificationEvent || notificationEvent.type !== "notification") return;
    const notification = mapNotification(notificationEvent.data);
    useNotificationStore.getState().addNotification(notification);
    toast(notification.text, { description: notificationEvent.data.notification_type_display });
  }, [notificationEvent]);

  const navLinkClass = ({ isActive }: { isActive: boolean }) =>
    cn(
      "rounded-full px-4 py-1.5 text-sm font-medium transition-colors",
      isActive
        ? "border border-border bg-surface-subtle font-semibold text-foreground"
        : "text-muted-foreground hover:text-foreground"
    );

  const mobileNavLinkClass = ({ isActive }: { isActive: boolean }) =>
    cn(
      "block rounded-full px-4 py-2 text-base font-medium transition-colors",
      isActive
        ? "border border-border bg-surface-subtle font-semibold text-foreground"
        : "text-muted-foreground hover:text-foreground"
    );

  return (
    <nav className="sticky top-0 z-[100] border-b border-border bg-card/95 backdrop-blur-md">
      <div className="flex h-16 items-center justify-between px-4 md:px-6 lg:px-8">
        <div
          className="flex shrink-0 cursor-pointer items-center gap-2"
          onClick={() => navigate("/")}
        >
          <div className="flex h-8 w-8 items-center justify-center rounded-md bg-brand text-brand-foreground shadow-xs">
            <Building2 className="size-4.5" />
          </div>
          <span className="font-display text-lg font-bold tracking-tight text-foreground sm:text-xl">
            Rentora
          </span>
          <BangladeshFlag className="h-4 w-auto sm:h-5" />
        </div>

        {/* Desktop nav links */}
        <div className="hidden items-center gap-1 md:flex">
          {NAV_KEYS.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.to === "/"} className={navLinkClass}>
              {t(item.key)}
            </NavLink>
          ))}
          {user && (
            <NavLink to="/dashboard" className={navLinkClass}>
              {t("nav.dashboard")}
            </NavLink>
          )}
          <div
            className="relative"
            onMouseEnter={() => setAreasOpen(true)}
            onMouseLeave={() => setAreasOpen(false)}
          >
            <button
              type="button"
              className={cn(
                "flex items-center gap-1 rounded-full px-4 py-1.5 text-sm font-medium transition-colors",
                areasOpen
                  ? "border border-border bg-surface-subtle text-foreground"
                  : "text-muted-foreground hover:text-foreground"
              )}
              aria-expanded={areasOpen}
            >
              {t("nav.areas")}
              <ChevronDown
                className={cn("size-3.5 transition-transform", areasOpen && "rotate-180")}
              />
            </button>
            {areasOpen && (
              <div className="absolute left-1/2 top-[calc(100%+8px)] z-[150] w-64 -translate-x-1/2 overflow-hidden rounded-xl border border-border bg-popover shadow-lg">
                <div className="border-b border-border px-4 py-2.5 text-xs font-bold tracking-wide text-muted-foreground uppercase">
                  Popular areas
                </div>
                <div className="grid grid-cols-2 gap-0.5 p-2">
                  {AREAS_INFO.map((area) => (
                    <NavLink
                      key={area.slug}
                      to={`/rooms/${area.slug}`}
                      className="rounded-md px-3 py-2 text-sm font-medium text-foreground transition-colors hover:bg-muted"
                      onClick={() => setAreasOpen(false)}
                    >
                      {area.area}
                    </NavLink>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Desktop actions */}
        <div className="hidden items-center gap-2 md:flex">
          <PwaInstallPrompt />
          <LanguageToggle />
          <Button
            variant="outline"
            size="icon"
            className="rounded-md"
            onClick={() => toggleDarkMode()}
          >
            {darkMode ? <Sun className="size-4" /> : <Moon className="size-4" />}
          </Button>

          <Button
            variant="outline"
            size="icon"
            className="relative rounded-md"
            onClick={() => navigate("/rooms")}
          >
            <Heart className="size-4" />
            {wishlist.length > 0 && (
              <Badge
                variant="brand"
                className="absolute -top-1.5 -right-1.5 h-[18px] min-w-[18px] justify-center rounded-full p-0 text-[10px]"
              >
                {wishlist.length}
              </Badge>
            )}
          </Button>

          <div className="relative">
            <Button
              variant="outline"
              size="icon"
              className="relative rounded-md"
              onClick={() => setShowNotif((v) => !v)}
            >
              <Bell className="size-4" />
              {unreadCount > 0 && (
                <Badge
                  variant="brand"
                  className="absolute -top-1.5 -right-1.5 h-[18px] min-w-[18px] justify-center rounded-full p-0 text-[10px]"
                >
                  {unreadCount}
                </Badge>
              )}
            </Button>
            {showNotif && (
              <div className="absolute right-0 top-[52px] z-[150] w-80 overflow-hidden rounded-xl border border-border bg-popover shadow-lg">
                <div className="flex items-center justify-between border-b border-border p-4 font-display text-sm font-bold text-foreground">
                  Notifications
                  <button
                    className="text-xs font-medium text-brand hover:underline cursor-pointer"
                    onClick={markAllRead}
                  >
                    Mark all read
                  </button>
                </div>
                {smartAlerts.length > 0 && smartAlerts[0].priority >= 70 && (
                  <div className="border-b border-warning/30 bg-warning/10 p-3">
                    <div className="mb-0.5 flex items-center justify-between">
                      <span className="text-[10px] font-bold tracking-wide text-warning uppercase">
                        ⚡ Top alert · priority {smartAlerts[0].priority}
                      </span>
                    </div>
                    <div className="text-xs font-semibold text-foreground">
                      {smartAlerts[0].title}
                    </div>
                    <div className="text-[11px] text-muted-foreground">
                      {smartAlerts[0].message} — <i>{smartAlerts[0].reason}</i>
                    </div>
                  </div>
                )}
                <div className="max-h-80 overflow-y-auto">
                  {notifications.map((n) => (
                    <div
                      key={n.id}
                      className={cn(
                        "flex gap-3 border-b border-border p-4 last:border-0 hover:bg-muted",
                        !n.read && "bg-brand/5"
                      )}
                    >
                      {!n.read && <div className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-brand" />}
                      <div className="flex-1">
                        <div className="text-sm leading-snug text-foreground">{n.text}</div>
                        <div className="mt-0.5 text-xs text-muted-foreground">{n.time}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {user ? (
            <div className="flex items-center gap-2">
              <div
                className="flex h-9 w-9 cursor-pointer items-center justify-center rounded-full bg-brand text-xs font-bold text-brand-foreground"
                onClick={() => navigate("/dashboard")}
              >
                {user.name.slice(0, 2).toUpperCase()}
              </div>
              <Button variant="outline" onClick={() => logout.mutate()}>
                {t("nav.logout")}
              </Button>
            </div>
          ) : (
            <Button variant="brand" onClick={() => navigate("/auth")}>
              {t("nav.signIn")}
            </Button>
          )}
        </div>

        {/* Mobile hamburger */}
        <Button
          variant="outline"
          size="icon"
          className="shrink-0 rounded-md md:hidden"
          onClick={() => setMobileOpen((v) => !v)}
          aria-label="Toggle menu"
        >
          {mobileOpen ? <X className="size-5" /> : <Menu className="size-5" />}
        </Button>
      </div>

      {/* Mobile menu panel */}
      {mobileOpen && (
        <div className="border-t border-border bg-card px-4 py-4 md:hidden">
          <div className="flex flex-col gap-1">
            {NAV_KEYS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                className={mobileNavLinkClass}
                onClick={() => setMobileOpen(false)}
              >
                {t(item.key)}
              </NavLink>
            ))}
            {user && (
              <NavLink
                to="/dashboard"
                className={mobileNavLinkClass}
                onClick={() => setMobileOpen(false)}
              >
                {t("nav.dashboard")}
              </NavLink>
            )}
          </div>

          <div className="mt-4 flex items-center gap-2 border-t border-border pt-4">
            <LanguageToggle />
            <Button
              variant="outline"
              size="icon"
              className="rounded-md"
              onClick={() => toggleDarkMode()}
            >
              {darkMode ? <Sun className="size-4" /> : <Moon className="size-4" />}
            </Button>
            <Button
              variant="outline"
              size="icon"
              className="relative rounded-md"
              onClick={() => {
                navigate("/rooms");
                setMobileOpen(false);
              }}
            >
              <Heart className="size-4" />
              {wishlist.length > 0 && (
                <Badge
                  variant="brand"
                  className="absolute -top-1.5 -right-1.5 h-[18px] min-w-[18px] justify-center rounded-full p-0 text-[10px]"
                >
                  {wishlist.length}
                </Badge>
              )}
            </Button>
            <Button
              variant="outline"
              size="icon"
              className="relative rounded-md"
              onClick={() => setShowNotif((v) => !v)}
            >
              <Bell className="size-4" />
              {unreadCount > 0 && (
                <Badge
                  variant="brand"
                  className="absolute -top-1.5 -right-1.5 h-[18px] min-w-[18px] justify-center rounded-full p-0 text-[10px]"
                >
                  {unreadCount}
                </Badge>
              )}
            </Button>
          </div>

          {showNotif && (
            <div className="mt-3 overflow-hidden rounded-xl border border-border bg-popover shadow-lg">
              <div className="flex items-center justify-between border-b border-border p-4 font-display text-sm font-bold text-foreground">
                Notifications
                <button
                  className="text-xs font-medium text-brand hover:underline cursor-pointer"
                  onClick={markAllRead}
                >
                  Mark all read
                </button>
              </div>
              <div className="max-h-64 overflow-y-auto">
                {notifications.map((n) => (
                  <div
                    key={n.id}
                    className={cn(
                      "flex gap-3 border-b border-border p-4 last:border-0",
                      !n.read && "bg-brand/5"
                    )}
                  >
                    {!n.read && <div className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-brand" />}
                    <div className="flex-1">
                      <div className="text-sm leading-snug text-foreground">{n.text}</div>
                      <div className="mt-0.5 text-xs text-muted-foreground">{n.time}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="mt-4 border-t border-border pt-4">
            {user ? (
              <Button variant="outline" className="w-full" onClick={() => logout.mutate()}>
                Logout
              </Button>
            ) : (
              <Button
                variant="brand"
                className="w-full"
                onClick={() => {
                  navigate("/auth");
                  setMobileOpen(false);
                }}
              >
                Sign In
              </Button>
            )}
          </div>
        </div>
      )}
    </nav>
  );
}
