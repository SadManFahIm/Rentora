import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Heart } from "lucide-react";
import { useDashboard } from "../../hooks/useDashboard";
import { useBookings } from "../../hooks/useBookings";
import { wishlistService } from "../../services/wishlistService";
import RoomCard from "../../components/RoomCard/RoomCard";
import RoomModal from "../../components/RoomModal/RoomModal";
import { Button } from "../../components/ui/button";
import type { Room } from "../../types";
import { cn } from "../../lib/utils";

type DashboardTab = "overview" | "bookings" | "wishlist";

interface StatCard {
  icon: string;
  label: string;
  value: string;
  change: string;
}

const statusClasses: Record<string, string> = {
  approved: "bg-emerald-500/10 text-emerald-500",
  pending: "bg-amber-500/10 text-amber-500",
  rejected: "bg-red-500/10 text-red-500",
  cancelled: "bg-gray-500/10 text-gray-500",
};

const takaFmt = (n: number) => `৳${n.toLocaleString()}`;

export default function Dashboard() {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<DashboardTab>("overview");
  const [selectedRoom, setSelectedRoom] = useState<Room | null>(null);

  const { data: stats, isLoading: statsLoading } = useDashboard();
  const { data: bookings = [], isLoading: bookingsLoading } = useBookings();
  const { data: wishlistedRooms = [], isLoading: wishlistLoading } = useQuery<Room[]>({
    queryKey: ["wishlist", "rooms"],
    queryFn: () => wishlistService.getWishlist(),
  });

  const na = statsLoading || !stats;

  const statCards: StatCard[] = [
    {
      icon: "🏠",
      label: "Saved Rooms",
      value: na ? "—" : String(stats.saved_rooms_count),
      change: na ? "" : `${stats.saved_rooms_count} in wishlist`,
    },
    {
      icon: "📅",
      label: "Booking Requests",
      value: na ? "—" : String(stats.active_bookings + stats.pending_bookings),
      change: na ? "" : `${stats.pending_bookings} pending`,
    },
    {
      icon: "🔔",
      label: "Unread Alerts",
      value: na ? "—" : String(stats.unread_notifications),
      change: na ? "" : `${stats.unread_notifications} new`,
    },
    {
      icon: "⭐",
      label: "Profile Score",
      value: na ? "—" : `${stats.profile_completion}%`,
      change: na ? "" : "Complete your profile",
    },
  ];

  const landlordCards: StatCard[] | null =
    stats?.landlord != null
      ? [
          { icon: "🏢", label: "My Listings", value: String(stats.landlord.total_listings), change: "" },
          { icon: "📨", label: "Bookings Received", value: String(stats.landlord.total_bookings_received), change: "" },
          { icon: "⭐", label: "Avg Rating", value: stats.landlord.avg_rating.toFixed(1), change: "" },
          { icon: "💰", label: "Revenue", value: takaFmt(stats.landlord.total_revenue), change: "approved bookings" },
        ]
      : null;

  const tabs: DashboardTab[] = ["overview", "bookings", "wishlist"];

  return (
    <div className="mx-auto max-w-7xl px-4 py-12 md:px-6 md:py-16 lg:px-8">
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold text-foreground">My Dashboard</h1>
          <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">Welcome back! Here's your activity.</p>
        </div>
        <Button className="bg-orange-600 text-white hover:bg-orange-700" onClick={() => navigate("/rooms")}>
          + List a Room
        </Button>
      </div>

      <div className="mb-6 flex w-fit gap-1 rounded-xl bg-gray-50 p-1 dark:bg-gray-800">
        {tabs.map((t) => (
          <button
            key={t}
            className={cn(
              "rounded-lg px-5 py-2 text-sm font-medium capitalize transition-colors",
              activeTab === t
                ? "bg-card text-foreground shadow-sm"
                : "text-gray-600 hover:text-foreground dark:text-gray-400"
            )}
            onClick={() => setActiveTab(t)}
          >
            {t}
          </button>
        ))}
      </div>

      {activeTab === "overview" && (
        <>
          <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {statCards.map((s) => (
              <div key={s.label} className="rounded-2xl border border-gray-200 bg-card p-5 dark:border-gray-800">
                <div className="mb-2.5 text-2xl">{s.icon}</div>
                <h3 className="font-display text-2xl font-bold text-foreground">{s.value}</h3>
                <p className="text-sm text-gray-600 dark:text-gray-400">{s.label}</p>
                {s.change && <div className="text-sm font-semibold text-emerald-500">{s.change}</div>}
              </div>
            ))}
          </div>

          {landlordCards && (
            <div className="mb-6">
              <h2 className="mb-3 font-display text-lg font-bold text-foreground">Landlord Overview</h2>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
                {landlordCards.map((s) => (
                  <div key={s.label} className="rounded-2xl border border-gray-200 bg-card p-5 dark:border-gray-800">
                    <div className="mb-2.5 text-2xl">{s.icon}</div>
                    <h3 className="font-display text-2xl font-bold text-foreground">{s.value}</h3>
                    <p className="text-sm text-gray-600 dark:text-gray-400">{s.label}</p>
                    {s.change && <div className="text-sm font-semibold text-emerald-500">{s.change}</div>}
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="rounded-2xl border border-gray-200 bg-card p-5 dark:border-gray-800">
            <h3 className="mb-2.5 font-display font-bold text-foreground">🤖 AI Profile Insights</h3>
            <p className="text-sm leading-relaxed text-gray-600 dark:text-gray-400">
              Based on your search history, you prefer <strong className="text-foreground">Studio rooms in Dhanmondi/Banani</strong> within
              ৳10K-20K budget. Complete your <strong className="text-foreground">KYC verification</strong> to get priority access to premium
              listings.
            </p>
          </div>
        </>
      )}

      {activeTab === "bookings" && (
        bookingsLoading ? (
          <div className="py-15 text-center text-gray-600 dark:text-gray-400">Loading bookings…</div>
        ) : bookings.length === 0 ? (
          <div className="flex flex-col items-center px-5 py-15 text-center text-gray-600 dark:text-gray-400">
            <span className="mb-4 text-5xl">📅</span>
            <h3 className="mb-2 font-display text-lg font-bold text-foreground">No bookings yet</h3>
            <p>Browse rooms and send a booking request to get started.</p>
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            {bookings.map((b) => (
              <div key={b.bookingId} className="flex flex-col gap-4 rounded-2xl border border-gray-200 bg-card p-5 dark:border-gray-800 sm:flex-row sm:items-center">
                <img src={b.img} alt={b.name} className="h-40 w-full shrink-0 rounded-lg object-cover sm:h-20 sm:w-25" />
                <div className="flex-1">
                  <h4 className="font-display text-sm font-bold text-foreground">{b.name}</h4>
                  <p className="my-1 text-sm text-gray-600 dark:text-gray-400">
                    Scheduled: {b.date} • ৳{b.monthlyRent.toLocaleString()}/mo
                  </p>
                  <span className={cn("inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold", statusClasses[b.status])}>
                    {b.status.charAt(0).toUpperCase() + b.status.slice(1)}
                  </span>
                </div>
                <div className="flex flex-col gap-2">
                  {b.status === "approved" && (
                    <Button className="bg-orange-600 text-white hover:bg-orange-700">Sign Agreement 📝</Button>
                  )}
                  <Button variant="outline">View Details</Button>
                </div>
              </div>
            ))}
          </div>
        )
      )}

      {activeTab === "wishlist" && (
        wishlistLoading ? (
          <div className="py-15 text-center text-gray-600 dark:text-gray-400">Loading saved rooms…</div>
        ) : wishlistedRooms.length === 0 ? (
          <div className="flex flex-col items-center px-5 py-15 text-center text-gray-600 dark:text-gray-400">
            <Heart className="mb-4 size-12" />
            <h3 className="mb-2 font-display text-lg font-bold text-foreground">No saved rooms yet</h3>
            <p>Tap the heart icon on any room to save it here.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {wishlistedRooms.map((r) => <RoomCard key={r.id} room={r} onClick={setSelectedRoom} />)}
          </div>
        )
      )}

      {selectedRoom && <RoomModal room={selectedRoom} onClose={() => setSelectedRoom(null)} />}
    </div>
  );
}
