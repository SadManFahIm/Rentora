import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useRooms } from "../../hooks/useRooms";
import { useBookings } from "../../hooks/useBookings";
import { useWishlistStore } from "../../stores/wishlistStore";
import RoomCard from "../../components/RoomCard/RoomCard";
import RoomModal from "../../components/RoomModal/RoomModal";
import type { Room } from "../../types";
import "./Dashboard.css";

type DashboardTab = "overview" | "bookings" | "wishlist";

interface StatCard {
  icon: string;
  label: string;
  value: string;
  change: string;
  up: boolean;
}

export default function Dashboard() {
  const { data: rooms = [] } = useRooms();
  const { data: bookings = [] } = useBookings();
  const wishlist = useWishlistStore((s) => s.wishlist);
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<DashboardTab>("overview");
  const [selectedRoom, setSelectedRoom] = useState<Room | null>(null);

  const wishlistedRooms = rooms.filter((r) => wishlist.includes(r.id));

  const stats: StatCard[] = [
    { icon: "🏠", label: "Saved Rooms", value: String(wishlistedRooms.length), change: "+2 this week", up: true },
    { icon: "📅", label: "Booking Requests", value: "1", change: "1 pending", up: true },
    { icon: "💬", label: "Unread Messages", value: "2", change: "2 new", up: true },
    { icon: "⭐", label: "Profile Score", value: "87%", change: "+5% this month", up: true },
  ];

  const tabs: DashboardTab[] = ["overview", "bookings", "wishlist"];

  return (
    <div className="section-container">
      <div className="dashboard-top">
        <div>
          <h1 className="dashboard-title">My Dashboard</h1>
          <p style={{ color: "var(--text2)", marginTop: 4 }}>Welcome back! Here's your activity.</p>
        </div>
        <button className="btn-primary" onClick={() => navigate("/rooms")}>+ List a Room</button>
      </div>

      <div className="tabs">
        {tabs.map((t) => (
          <button key={t} className={`tab ${activeTab === t ? "active" : ""}`} onClick={() => setActiveTab(t)}>
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      {activeTab === "overview" && (
        <>
          <div className="stats-grid">
            {stats.map((s) => (
              <div key={s.label} className="stat-card">
                <div className="stat-icon">{s.icon}</div>
                <h3>{s.value}</h3>
                <p>{s.label}</p>
                <div className={`stat-change ${s.up ? "" : "down"}`}>{s.change}</div>
              </div>
            ))}
          </div>
          <div className="ai-insight">
            <h3>🤖 AI Profile Insights</h3>
            <p>Based on your search history, you prefer <strong>Studio rooms in Dhanmondi/Banani</strong> within ৳10K-20K budget. There are <strong>3 new listings</strong> matching your profile today. Consider completing <strong>KYC verification</strong> to get priority access to premium listings.</p>
          </div>
        </>
      )}

      {activeTab === "bookings" && (
        <div className="bookings-list">
          {bookings.map((b) => (
            <div key={b.id} className="booking-card">
              <img src={b.img} alt={b.name} className="booking-img" />
              <div className="booking-info">
                <h4>{b.name}</h4>
                <p className="booking-meta">Scheduled: {b.date} • ৳{b.price.toLocaleString()}/mo</p>
                <span className={`booking-status ${b.status}`}>
                  {b.status.charAt(0).toUpperCase() + b.status.slice(1)}
                </span>
              </div>
              <div className="booking-actions">
                {b.status === "approved" && (
                  <button className="btn-primary" style={{ padding: "8px 16px", fontSize: "0.85rem" }}>
                    Sign Agreement 📝
                  </button>
                )}
                <button className="btn-outline" style={{ padding: "8px 16px", fontSize: "0.85rem" }}>
                  View Details
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {activeTab === "wishlist" && (
        wishlistedRooms.length === 0 ? (
          <div style={{ textAlign: "center", padding: "60px 20px", color: "var(--text2)" }}>
            <div style={{ fontSize: "3rem", marginBottom: 16 }}>🤍</div>
            <h3 style={{ fontFamily: "var(--font)", marginBottom: 8 }}>No saved rooms yet</h3>
            <p>Tap the heart icon on any room to save it here.</p>
          </div>
        ) : (
          <div className="rooms-grid">
            {wishlistedRooms.map((r) => <RoomCard key={r.id} room={r} onClick={setSelectedRoom} />)}
          </div>
        )
      )}

      {selectedRoom && <RoomModal room={selectedRoom} onClose={() => setSelectedRoom(null)} />}
    </div>
  );
}
