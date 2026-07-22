import { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { Menu, X, Sun, Moon, Heart, Bell } from "lucide-react";
import { useApp } from "../../context/AppContext";
import { useUiStore } from "../../stores/uiStore";
import { useWishlistStore } from "../../stores/wishlistStore";
import { useNotificationStore } from "../../stores/notificationStore";
import { useLogout } from "../../hooks/useAuth";
import { Button } from "../ui/button";
import { Badge } from "../ui/badge";
import { cn } from "../../lib/utils";

const NAV_ITEMS: { label: string; to: string }[] = [
  { label: "Home", to: "/" },
  { label: "Rooms", to: "/rooms" },
  { label: "Map", to: "/map" },
  { label: "Chat", to: "/chat" },
];

export default function Navbar() {
  const { user } = useApp();
  const darkMode = useUiStore((s) => s.darkMode);
  const toggleDarkMode = useUiStore((s) => s.toggleDarkMode);
  const wishlist = useWishlistStore((s) => s.wishlist);
  const notifications = useNotificationStore((s) => s.notifications);
  const markAllRead = useNotificationStore((s) => s.markAllRead);
  const logout = useLogout();

  const [showNotif, setShowNotif] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const navigate = useNavigate();
  const unreadCount = notifications.filter((n) => !n.read).length;

  const navLinkClass = ({ isActive }: { isActive: boolean }) =>
    cn(
      "rounded-lg px-4 py-2 text-sm font-medium transition-colors",
      isActive ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground"
    );

  const mobileNavLinkClass = ({ isActive }: { isActive: boolean }) =>
    cn(
      "block rounded-lg px-4 py-3 text-base font-medium transition-colors",
      isActive ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground"
    );

  return (
    <nav className="sticky top-0 z-[100] border-b border-border bg-card/95 backdrop-blur-md">
      <div className="flex h-16 items-center justify-between px-4 sm:px-8">
        <div
          className="flex shrink-0 cursor-pointer items-center gap-2 font-display text-lg font-extrabold tracking-tight text-brand sm:text-xl"
          onClick={() => navigate("/")}
        >
          🏠 RentRoom <Badge variant="brand">BD</Badge>
        </div>

        {/* Desktop nav links */}
        <div className="hidden items-center gap-1 md:flex">
          {NAV_ITEMS.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.to === "/"} className={navLinkClass}>
              {item.label}
            </NavLink>
          ))}
          {user && (
            <NavLink to="/dashboard" className={navLinkClass}>
              Dashboard
            </NavLink>
          )}
        </div>

        {/* Desktop actions */}
        <div className="hidden items-center gap-2 md:flex">
          <Button variant="outline" size="icon" className="rounded-xl" onClick={() => toggleDarkMode()}>
            {darkMode ? <Sun className="size-4" /> : <Moon className="size-4" />}
          </Button>

          <Button variant="outline" size="icon" className="relative rounded-xl" onClick={() => navigate("/rooms")}>
            <Heart className="size-4" />
            {wishlist.length > 0 && (
              <Badge variant="brand" className="absolute -top-1.5 -right-1.5 h-[18px] min-w-[18px] justify-center rounded-full p-0 text-[10px]">
                {wishlist.length}
              </Badge>
            )}
          </Button>

          <div className="relative">
            <Button
              variant="outline"
              size="icon"
              className="relative rounded-xl"
              onClick={() => setShowNotif((v) => !v)}
            >
              <Bell className="size-4" />
              {unreadCount > 0 && (
                <Badge variant="brand" className="absolute -top-1.5 -right-1.5 h-[18px] min-w-[18px] justify-center rounded-full p-0 text-[10px]">
                  {unreadCount}
                </Badge>
              )}
            </Button>
            {showNotif && (
              <div className="absolute right-0 top-[52px] z-[150] w-80 overflow-hidden rounded-2xl border border-border bg-popover shadow-lg">
                <div className="flex items-center justify-between border-b border-border p-4 font-display text-sm font-bold">
                  Notifications
                  <button
                    className="text-xs font-medium text-brand hover:underline"
                    onClick={markAllRead}
                  >
                    Mark all read
                  </button>
                </div>
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
                className="flex h-9 w-9 cursor-pointer items-center justify-center rounded-full bg-linear-to-br from-brand to-brand-dark text-xs font-bold text-white"
                onClick={() => navigate("/dashboard")}
              >
                {user.name.slice(0, 2).toUpperCase()}
              </div>
              <Button variant="outline" onClick={() => logout.mutate()}>
                Logout
              </Button>
            </div>
          ) : (
            <Button variant="brand" onClick={() => navigate("/auth")}>
              Sign In
            </Button>
          )}
        </div>

        {/* Mobile hamburger */}
        <Button
          variant="outline"
          size="icon"
          className="shrink-0 rounded-xl md:hidden"
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
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                className={mobileNavLinkClass}
                onClick={() => setMobileOpen(false)}
              >
                {item.label}
              </NavLink>
            ))}
            {user && (
              <NavLink to="/dashboard" className={mobileNavLinkClass} onClick={() => setMobileOpen(false)}>
                Dashboard
              </NavLink>
            )}
          </div>

          <div className="mt-4 flex items-center gap-2 border-t border-border pt-4">
            <Button variant="outline" size="icon" className="rounded-xl" onClick={() => toggleDarkMode()}>
              {darkMode ? <Sun className="size-4" /> : <Moon className="size-4" />}
            </Button>
            <Button
              variant="outline"
              size="icon"
              className="relative rounded-xl"
              onClick={() => {
                navigate("/rooms");
                setMobileOpen(false);
              }}
            >
              <Heart className="size-4" />
              {wishlist.length > 0 && (
                <Badge variant="brand" className="absolute -top-1.5 -right-1.5 h-[18px] min-w-[18px] justify-center rounded-full p-0 text-[10px]">
                  {wishlist.length}
                </Badge>
              )}
            </Button>
            <Button
              variant="outline"
              size="icon"
              className="relative rounded-xl"
              onClick={() => setShowNotif((v) => !v)}
            >
              <Bell className="size-4" />
              {unreadCount > 0 && (
                <Badge variant="brand" className="absolute -top-1.5 -right-1.5 h-[18px] min-w-[18px] justify-center rounded-full p-0 text-[10px]">
                  {unreadCount}
                </Badge>
              )}
            </Button>
          </div>

          {showNotif && (
            <div className="mt-3 overflow-hidden rounded-2xl border border-border bg-popover shadow-lg">
              <div className="flex items-center justify-between border-b border-border p-4 font-display text-sm font-bold">
                Notifications
                <button className="text-xs font-medium text-brand hover:underline" onClick={markAllRead}>
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
