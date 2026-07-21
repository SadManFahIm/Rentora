import { useState } from "react";
import { useApp } from "../../context/AppContext";
import "./Navbar.css";

export default function Navbar({ page, setPage }) {
  const { darkMode, setDarkMode, wishlist, notifications, user, setUser, markAllRead } = useApp();
  const [showNotif, setShowNotif] = useState(false);
  const unreadCount = notifications.filter((n) => !n.read).length;

  return (
    <nav className="navbar">
      <div className="navbar-brand" onClick={() => setPage("home")}>
        🏠 RentRoom <span className="navbar-badge">BD</span>
      </div>

      <div className="nav-links">
        {["home", "rooms", "map", "chat"].map((p) => (
          <button
            key={p}
            className={`nav-link ${page === p ? "active" : ""}`}
            onClick={() => setPage(p)}
          >
            {p.charAt(0).toUpperCase() + p.slice(1)}
          </button>
        ))}
        {user && (
          <button
            className={`nav-link ${page === "dashboard" ? "active" : ""}`}
            onClick={() => setPage("dashboard")}
          >
            Dashboard
          </button>
        )}
      </div>

      <div className="nav-actions">
        {/* Dark Mode */}
        <button className="icon-btn" onClick={() => setDarkMode(!darkMode)}>
          {darkMode ? "☀️" : "🌙"}
        </button>

        {/* Wishlist */}
        <button className="icon-btn" onClick={() => setPage("rooms")}>
          ❤️ {wishlist.length > 0 && <span className="badge">{wishlist.length}</span>}
        </button>

        {/* Notifications */}
        <div style={{ position: "relative" }}>
          <button className="icon-btn" onClick={() => setShowNotif(!showNotif)}>
            🔔 {unreadCount > 0 && <span className="badge">{unreadCount}</span>}
          </button>
          {showNotif && (
            <div className="notif-dropdown">
              <div className="notif-header">
                Notifications
                <button className="notif-mark-read" onClick={markAllRead}>
                  Mark all read
                </button>
              </div>
              {notifications.map((n) => (
                <div key={n.id} className={`notif-item ${!n.read ? "unread" : ""}`}>
                  {!n.read && <div className="notif-dot" />}
                  <div style={{ flex: 1 }}>
                    <div className="notif-text">{n.text}</div>
                    <div className="notif-time">{n.time}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Auth */}
        {user ? (
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div
              className="owner-avatar"
              style={{ width: 36, height: 36, cursor: "pointer" }}
              onClick={() => setPage("dashboard")}
            >
              {user.name.slice(0, 2).toUpperCase()}
            </div>
            <button className="btn-outline" onClick={() => setUser(null)} style={{ padding: "8px 14px" }}>
              Logout
            </button>
          </div>
        ) : (
          <button className="btn-primary" onClick={() => setPage("auth")}>
            Sign In
          </button>
        )}
      </div>
    </nav>
  );
}
