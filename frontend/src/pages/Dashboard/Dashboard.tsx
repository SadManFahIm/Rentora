import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Heart } from "lucide-react";
import { useRooms } from "../../hooks/useRooms";
import { useBookings } from "../../hooks/useBookings";
import { useWishlistStore } from "../../stores/wishlistStore";
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
  up: boolean;
}

const statusClasses: Record<string, string> = {
  approved: "bg-emerald-500/10 text-emerald-500",
  pending: "bg-amber-500/10 text-amber-500",
  rejected: "bg-red-500/10 text-red-500",
};

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
    <div className="mx-auto max-w-300 px-4 py-8 sm:px-8">
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="font-display text-2xl font-extrabold text-foreground">My Dashboard</h1>
          <p className="mt-1 text-sm text-muted-foreground">Welcome back! Here's your activity.</p>
        </div>
        <Button variant="brand" onClick={() => navigate("/rooms")}>
          + List a Room
        </Button>
      </div>

      <div className="mb-6 flex w-fit gap-1 rounded-xl bg-muted p-1">
        {tabs.map((t) => (
          <button
            key={t}
            className={cn(
              "rounded-lg px-5 py-2 text-sm font-medium capitalize transition-colors",
              activeTab === t ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
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
            {stats.map((s) => (
              <div key={s.label} className="rounded-2xl border border-border bg-card p-5">
                <div className="mb-2.5 text-2xl">{s.icon}</div>
                <h3 className="font-display text-2xl font-extrabold text-foreground">{s.value}</h3>
                <p className="text-sm text-muted-foreground">{s.label}</p>
                <div className={cn("text-sm font-semibold", s.up ? "text-emerald-500" : "text-red-500")}>
                  {s.change}
                </div>
              </div>
            ))}
          </div>
          <div className="rounded-2xl border border-border bg-card p-5">
            <h3 className="mb-2.5 font-display font-bold text-foreground">🤖 AI Profile Insights</h3>
            <p className="text-sm leading-relaxed text-muted-foreground">
              Based on your search history, you prefer <strong className="text-foreground">Studio rooms in Dhanmondi/Banani</strong> within
              ৳10K-20K budget. There are <strong className="text-foreground">3 new listings</strong> matching your profile today. Consider
              completing <strong className="text-foreground">KYC verification</strong> to get priority access to premium listings.
            </p>
          </div>
        </>
      )}

      {activeTab === "bookings" && (
        <div className="flex flex-col gap-4">
          {bookings.map((b) => (
            <div key={b.id} className="flex flex-col gap-4 rounded-2xl border border-border bg-card p-5 sm:flex-row sm:items-center">
              <img src={b.img} alt={b.name} className="h-40 w-full shrink-0 rounded-lg object-cover sm:h-20 sm:w-25" />
              <div className="flex-1">
                <h4 className="font-display text-sm font-bold text-foreground">{b.name}</h4>
                <p className="my-1 text-sm text-muted-foreground">
                  Scheduled: {b.date} • ৳{b.price.toLocaleString()}/mo
                </p>
                <span className={cn("inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold", statusClasses[b.status])}>
                  {b.status.charAt(0).toUpperCase() + b.status.slice(1)}
                </span>
              </div>
              <div className="flex flex-col gap-2">
                {b.status === "approved" && <Button variant="brand">Sign Agreement 📝</Button>}
                <Button variant="outline">View Details</Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {activeTab === "wishlist" && (
        wishlistedRooms.length === 0 ? (
          <div className="flex flex-col items-center px-5 py-15 text-center text-muted-foreground">
            <Heart className="mb-4 size-12" />
            <h3 className="mb-2 font-display text-lg font-bold text-foreground">No saved rooms yet</h3>
            <p>Tap the heart icon on any room to save it here.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {wishlistedRooms.map((r) => <RoomCard key={r.id} room={r} onClick={setSelectedRoom} />)}
          </div>
        )
      )}

      {selectedRoom && <RoomModal room={selectedRoom} onClose={() => setSelectedRoom(null)} />}
    </div>
  );
}
