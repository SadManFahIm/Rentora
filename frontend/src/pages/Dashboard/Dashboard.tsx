import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Download,
  Heart,
  Loader2,
  Megaphone,
  ShieldAlert,
  ShieldCheck,
  KeyRound,
} from "lucide-react";
import { useDashboard } from "../../hooks/useDashboard";
import { useRooms } from "../../hooks/useRooms";
import { useBookings } from "../../hooks/useBookings";
import { useFraudReports, useReviewFraudReport, useScanRoom } from "../../hooks/useFraud";
import {
  useDepositStatus,
  useDownloadReceipt,
  usePaymentHistory,
  usePaymentSummary,
} from "../../hooks/usePayments";
import { wishlistService } from "../../services/wishlistService";
import { useApp } from "../../context/AppContext";
import RoomCard from "../../components/RoomCard/RoomCard";
import RoomModal from "../../components/RoomModal/RoomModal";
import TierBadge from "../../components/TierBadge/TierBadge";
import PromoteModal from "../../components/PromoteModal/PromoteModal";
import PaymentMethodModal, {
  type PaymentRequest,
} from "../../components/PaymentMethodModal/PaymentMethodModal";
import { Button } from "../../components/ui/button";
import { Skeleton } from "../../components/ui/skeleton";
import { Input } from "../../components/ui/input";
import { toast } from "sonner";
import { authService } from "../../services/authService";
import { getApiErrorMessage } from "../../services/errors";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../../components/ui/select";
import type { Booking, PaymentStatus, Room } from "../../types";
import { cn } from "../../lib/utils";

type DashboardTab = "overview" | "listings" | "bookings" | "payments" | "wishlist" | "fraud";
const TABS: DashboardTab[] = ["overview", "listings", "bookings", "payments", "wishlist", "fraud"];

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

const paymentStatusClasses: Record<PaymentStatus, string> = {
  initiated: "bg-gray-500/10 text-gray-500",
  pending: "bg-amber-500/10 text-amber-500",
  success: "bg-emerald-500/10 text-emerald-500",
  failed: "bg-red-500/10 text-red-500",
  cancelled: "bg-gray-500/10 text-gray-500",
  refunded: "bg-blue-500/10 text-blue-500",
};

const paymentMethodLabels: Record<string, string> = {
  sslcommerz: "SSLCommerz",
  bkash: "bKash",
  nagad: "Nagad",
  manual: "Manual",
};

const paymentTypeLabels: Record<string, string> = {
  monthly_rent: "Monthly Rent",
  security_deposit: "Security Deposit",
  booking_deposit: "Booking Deposit",
  listing_feature: "Listing Promotion (Featured)",
  listing_premium: "Listing Promotion (Premium)",
};

const takaFmt = (n: number) => `৳${n.toLocaleString()}`;

function formatPaymentDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

/** One booking's row in the "bookings" tab. Deposit status is fetched per
 * booking (`GET /bookings/:id/deposit-status/`) so the badge always reflects
 * the authoritative, live state rather than whatever was last cached on the
 * booking list. */
function BookingListItem({
  booking,
  onPayNow,
  onPayDeposit,
}: {
  booking: Booking;
  onPayNow: (booking: Booking) => void;
  onPayDeposit: (booking: Booking) => void;
}) {
  const { data: deposit } = useDepositStatus(booking.bookingId);

  const depositAmount = deposit?.securityDepositAmount ?? booking.securityDepositAmount;
  const depositPaid = deposit?.securityDepositPaid ?? booking.securityDepositPaid;
  const depositRefunded = deposit?.securityDepositRefunded ?? booking.securityDepositRefunded;
  const hasDeposit = depositAmount > 0;

  return (
    <div className="flex flex-col gap-4 rounded-2xl border border-gray-200 bg-card p-5 dark:border-gray-800 sm:flex-row sm:items-center">
      <img
        src={booking.img}
        alt={booking.name}
        className="h-40 w-full shrink-0 rounded-lg object-cover sm:h-20 sm:w-25"
      />
      <div className="flex-1">
        <h4 className="font-display text-sm font-bold text-foreground">{booking.name}</h4>
        <p className="my-1 text-sm text-gray-600 dark:text-gray-400">
          Scheduled: {booking.date} • ৳{booking.monthlyRent.toLocaleString()}/mo
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <span
            className={cn(
              "inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold",
              statusClasses[booking.status]
            )}
          >
            {booking.status.charAt(0).toUpperCase() + booking.status.slice(1)}
          </span>
          {hasDeposit && (
            <span
              className={cn(
                "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold",
                depositRefunded
                  ? "bg-blue-500/10 text-blue-500"
                  : depositPaid
                    ? "bg-emerald-500/10 text-emerald-500"
                    : "bg-amber-500/10 text-amber-500"
              )}
            >
              <ShieldCheck className="size-3" />
              Deposit {depositRefunded ? "Refunded" : depositPaid ? "Paid" : "Unpaid"}
            </span>
          )}
        </div>
      </div>
      <div className="flex flex-col gap-2">
        {booking.status === "approved" && (
          <>
            <Button
              className="bg-orange-600 text-white hover:bg-orange-700"
              onClick={() => onPayNow(booking)}
            >
              Pay Now
            </Button>
            <Button variant="outline">Sign Agreement 📝</Button>
          </>
        )}
        {hasDeposit && !depositPaid && !depositRefunded && (
          <Button variant="outline" onClick={() => onPayDeposit(booking)}>
            Pay Deposit
          </Button>
        )}
        <Button variant="outline">View Details</Button>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const requestedTab = searchParams.get("tab");
  const [activeTab, setActiveTab] = useState<DashboardTab>(
    (TABS as string[]).includes(requestedTab ?? "") ? (requestedTab as DashboardTab) : "overview"
  );
  const [selectedRoom, setSelectedRoom] = useState<Room | null>(null);
  const [payRequest, setPayRequest] = useState<PaymentRequest | null>(null);
  const [promoteRoom, setPromoteRoom] = useState<Room | null>(null);

  const [statusFilter, setStatusFilter] = useState<PaymentStatus | "all">("all");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const { data: stats, isLoading: statsLoading } = useDashboard();
  const { data: bookings = [], isLoading: bookingsLoading } = useBookings();
  const { data: wishlistedRooms = [], isLoading: wishlistLoading } = useQuery<Room[]>({
    queryKey: ["wishlist", "rooms"],
    queryFn: () => wishlistService.getWishlist(),
  });

  const paymentFilters = {
    ...(statusFilter !== "all" ? { status: statusFilter } : {}),
    ...(dateFrom ? { dateFrom } : {}),
    ...(dateTo ? { dateTo } : {}),
  };
  const { data: payments = [], isLoading: paymentsLoading } = usePaymentHistory(paymentFilters);
  const { data: summary, isLoading: summaryLoading } = usePaymentSummary();
  const downloadReceipt = useDownloadReceipt();

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
          {
            icon: "🏢",
            label: "My Listings",
            value: String(stats.landlord.total_listings),
            change: "",
          },
          {
            icon: "📨",
            label: "Bookings Received",
            value: String(stats.landlord.total_bookings_received),
            change: "",
          },
          {
            icon: "⭐",
            label: "Avg Rating",
            value: stats.landlord.avg_rating.toFixed(1),
            change: "",
          },
          {
            icon: "💰",
            label: "Revenue",
            value: takaFmt(stats.landlord.total_revenue),
            change: "approved bookings",
          },
        ]
      : null;

  const handlePayNow = (booking: Booking) => {
    setPayRequest({
      bookingId: booking.bookingId,
      paymentType: "monthly_rent",
      amount: booking.monthlyRent,
      roomName: booking.name,
    });
  };

  const handlePayDeposit = (booking: Booking) => {
    setPayRequest({
      bookingId: booking.bookingId,
      paymentType: "security_deposit",
      amount: booking.securityDepositAmount,
      roomName: booking.name,
    });
  };

  return (
    <div className="mx-auto max-w-7xl px-4 py-12 md:px-6 md:py-16 lg:px-8">
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold text-foreground">My Dashboard</h1>
          <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
            Welcome back! Here's your activity.
          </p>
        </div>
        <Button
          className="bg-orange-600 text-white hover:bg-orange-700"
          onClick={() => navigate("/rooms")}
        >
          + List a Room
        </Button>
      </div>

      <div className="mb-6 flex w-fit gap-1 rounded-xl bg-gray-50 p-1 dark:bg-gray-800">
        {TABS.map((t) => (
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
              <div
                key={s.label}
                className="rounded-2xl border border-gray-200 bg-card p-5 dark:border-gray-800"
              >
                <div className="mb-2.5 text-2xl">{s.icon}</div>
                <h3 className="font-display text-2xl font-bold text-foreground">{s.value}</h3>
                <p className="text-sm text-gray-600 dark:text-gray-400">{s.label}</p>
                {s.change && (
                  <div className="text-sm font-semibold text-emerald-500">{s.change}</div>
                )}
              </div>
            ))}
          </div>

          {landlordCards && (
            <div className="mb-6">
              <h2 className="mb-3 font-display text-lg font-bold text-foreground">
                Landlord Overview
              </h2>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
                {landlordCards.map((s) => (
                  <div
                    key={s.label}
                    className="rounded-2xl border border-gray-200 bg-card p-5 dark:border-gray-800"
                  >
                    <div className="mb-2.5 text-2xl">{s.icon}</div>
                    <h3 className="font-display text-2xl font-bold text-foreground">{s.value}</h3>
                    <p className="text-sm text-gray-600 dark:text-gray-400">{s.label}</p>
                    {s.change && (
                      <div className="text-sm font-semibold text-emerald-500">{s.change}</div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="rounded-2xl border border-gray-200 bg-card p-5 dark:border-gray-800">
            <h3 className="mb-2.5 font-display font-bold text-foreground">
              🤖 AI Profile Insights
            </h3>
            <p className="text-sm leading-relaxed text-gray-600 dark:text-gray-400">
              Based on your search history, you prefer{" "}
              <strong className="text-foreground">Studio rooms in Dhanmondi/Banani</strong> within
              ৳10K-20K budget. Complete your{" "}
              <strong className="text-foreground">KYC verification</strong> to get priority access
              to premium listings.
            </p>
          </div>

          <div className="mt-6">
            <TwoFactorCard />
          </div>
        </>
      )}

      {activeTab === "listings" && <ListingsTab onPromote={setPromoteRoom} />}

      {activeTab === "bookings" &&
        (bookingsLoading ? (
          <div className="py-15 text-center text-gray-600 dark:text-gray-400">
            Loading bookings…
          </div>
        ) : bookings.length === 0 ? (
          <div className="flex flex-col items-center px-5 py-15 text-center text-gray-600 dark:text-gray-400">
            <span className="mb-4 text-5xl">📅</span>
            <h3 className="mb-2 font-display text-lg font-bold text-foreground">No bookings yet</h3>
            <p>Browse rooms and send a booking request to get started.</p>
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            {bookings.map((b) => (
              <BookingListItem
                key={b.bookingId}
                booking={b}
                onPayNow={handlePayNow}
                onPayDeposit={handlePayDeposit}
              />
            ))}
          </div>
        ))}

      {activeTab === "payments" && (
        <>
          <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="rounded-2xl border border-gray-200 bg-card p-5 dark:border-gray-800">
              <div className="text-sm text-gray-600 dark:text-gray-400">Total Paid</div>
              {summaryLoading ? (
                <Skeleton className="mt-2 h-8 w-28" />
              ) : (
                <div className="font-display text-2xl font-bold text-emerald-500">
                  {takaFmt(summary?.totalPaid ?? 0)}
                </div>
              )}
            </div>
            <div className="rounded-2xl border border-gray-200 bg-card p-5 dark:border-gray-800">
              <div className="text-sm text-gray-600 dark:text-gray-400">Pending</div>
              {summaryLoading ? (
                <Skeleton className="mt-2 h-8 w-28" />
              ) : (
                <div className="font-display text-2xl font-bold text-amber-500">
                  {takaFmt(summary?.totalPending ?? 0)}
                </div>
              )}
            </div>
            <div className="rounded-2xl border border-gray-200 bg-card p-5 dark:border-gray-800">
              <div className="text-sm text-gray-600 dark:text-gray-400">Refunded</div>
              {summaryLoading ? (
                <Skeleton className="mt-2 h-8 w-28" />
              ) : (
                <div className="font-display text-2xl font-bold text-blue-500">
                  {takaFmt(summary?.totalRefunded ?? 0)}
                </div>
              )}
            </div>
          </div>

          <div className="mb-4 flex flex-wrap items-center gap-3">
            <Select
              value={statusFilter}
              onValueChange={(v) => setStatusFilter(v as PaymentStatus | "all")}
            >
              <SelectTrigger className="w-40">
                <SelectValue placeholder="All statuses" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                <SelectItem value="success">Success</SelectItem>
                <SelectItem value="pending">Pending</SelectItem>
                <SelectItem value="initiated">Initiated</SelectItem>
                <SelectItem value="failed">Failed</SelectItem>
                <SelectItem value="cancelled">Cancelled</SelectItem>
                <SelectItem value="refunded">Refunded</SelectItem>
              </SelectContent>
            </Select>
            <div className="flex items-center gap-2">
              <Input
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                className="w-40"
                aria-label="From date"
              />
              <span className="text-sm text-gray-500">to</span>
              <Input
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                className="w-40"
                aria-label="To date"
              />
            </div>
          </div>

          {paymentsLoading ? (
            <div className="flex flex-col gap-3">
              {[0, 1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-20 w-full rounded-xl" />
              ))}
            </div>
          ) : payments.length === 0 ? (
            <div className="flex flex-col items-center px-5 py-15 text-center text-gray-600 dark:text-gray-400">
              <span className="mb-4 text-5xl">💳</span>
              <h3 className="mb-2 font-display text-lg font-bold text-foreground">
                No payments yet
              </h3>
              <p>Your payment history will show up here.</p>
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              {payments.map((p) => {
                const isDownloading =
                  downloadReceipt.isPending && downloadReceipt.variables === p.id;
                return (
                  <div
                    key={p.id}
                    className="flex flex-col gap-3 rounded-xl border border-gray-200 bg-card p-4 dark:border-gray-800 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div className="flex-1">
                      <div className="text-sm font-semibold text-foreground">
                        {formatPaymentDate(p.createdAt)}
                      </div>
                      <div className="text-xs text-gray-600 dark:text-gray-400">
                        {paymentMethodLabels[p.method] ?? p.method} •{" "}
                        {paymentTypeLabels[p.type] ?? p.type}
                      </div>
                    </div>
                    <div className="font-display font-bold text-foreground">
                      {takaFmt(p.amount)}
                    </div>
                    <span
                      className={cn(
                        "inline-flex w-fit rounded-full px-2.5 py-0.5 text-xs font-semibold",
                        paymentStatusClasses[p.status]
                      )}
                    >
                      {p.status.charAt(0).toUpperCase() + p.status.slice(1)}
                    </span>
                    {p.status === "success" && (
                      <button
                        type="button"
                        onClick={() => downloadReceipt.mutate(p.id)}
                        disabled={isDownloading}
                        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-gray-200 text-gray-600 transition-colors hover:bg-gray-50 disabled:opacity-50 dark:border-gray-800 dark:text-gray-400 dark:hover:bg-gray-800"
                        aria-label="Download receipt"
                      >
                        {isDownloading ? (
                          <Loader2 className="size-4 animate-spin" />
                        ) : (
                          <Download className="size-4" />
                        )}
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}

      {activeTab === "wishlist" &&
        (wishlistLoading ? (
          <div className="py-15 text-center text-gray-600 dark:text-gray-400">
            Loading saved rooms…
          </div>
        ) : wishlistedRooms.length === 0 ? (
          <div className="flex flex-col items-center px-5 py-15 text-center text-gray-600 dark:text-gray-400">
            <Heart className="mb-4 size-12" />
            <h3 className="mb-2 font-display text-lg font-bold text-foreground">
              No saved rooms yet
            </h3>
            <p>Tap the heart icon on any room to save it here.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {wishlistedRooms.map((r) => (
              <RoomCard key={r.id} room={r} onClick={setSelectedRoom} />
            ))}
          </div>
        ))}

      {activeTab === "fraud" && <FraudTab />}

      {selectedRoom && <RoomModal room={selectedRoom} onClose={() => setSelectedRoom(null)} />}
      <PaymentMethodModal request={payRequest} onClose={() => setPayRequest(null)} />
      <PromoteModal
        room={promoteRoom}
        onClose={() => setPromoteRoom(null)}
        onPromoted={(roomId) => {
          // Room tier changed server-side after a successful payment; refresh
          // the landlord's listings list.
          queryClient.invalidateQueries({ queryKey: ["rooms"] });
          void roomId;
        }}
      />
    </div>
  );
}

/** Account security: enable/disable email-OTP two-factor authentication.
 * Enabling asks for the current password (the backend enforces it too). */
function TwoFactorCard() {
  const { user, setUser } = useApp();
  const [enabling, setEnabling] = useState(false);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  const enabled = user?.otpEnabled === true;

  const enable = async () => {
    setBusy(true);
    try {
      const result = await authService.toggle2fa(true, password);
      setUser({ ...user!, otpEnabled: result.otpEnabled });
      setEnabling(false);
      setPassword("");
      toast.success("Two-factor authentication enabled.");
    } catch (error) {
      toast.error(getApiErrorMessage(error, "Could not enable 2FA. Check your current password."));
    } finally {
      setBusy(false);
    }
  };

  const disable = async () => {
    setBusy(true);
    try {
      const result = await authService.toggle2fa(false);
      setUser({ ...user!, otpEnabled: result.otpEnabled });
      toast.success("Two-factor authentication disabled.");
    } catch {
      toast.error("Could not disable 2FA right now.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-4 rounded-2xl border border-gray-200 bg-card p-5 dark:border-gray-800 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex items-start gap-3">
        <span
          className={cn(
            "inline-flex size-10 shrink-0 items-center justify-center rounded-xl",
            enabled
              ? "bg-emerald-500/10 text-emerald-500"
              : "bg-gray-100 text-gray-500 dark:bg-gray-800"
          )}
        >
          <KeyRound className="size-5" />
        </span>
        <div>
          <h3 className="font-display text-sm font-bold text-foreground">
            Two-Factor Authentication
          </h3>
          <p className="mt-0.5 max-w-md text-sm text-gray-600 dark:text-gray-400">
            {enabled
              ? "On — signing in also requires a one-time code emailed to you."
              : "Off — add an extra security layer: signing in will also require a one-time code emailed to you."}
          </p>
          {enabled && (
            <span className="mt-2 inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-xs font-semibold text-emerald-500">
              <ShieldCheck className="size-3" /> Enabled
            </span>
          )}
        </div>
      </div>

      <div className="shrink-0">
        {enabled ? (
          <Button variant="outline" size="sm" onClick={disable} disabled={busy}>
            {busy ? <Loader2 className="size-3.5 animate-spin" /> : "Disable"}
          </Button>
        ) : enabling ? (
          <div className="flex items-center gap-2">
            <Input
              type="password"
              placeholder="Current password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-44"
              autoComplete="current-password"
              aria-label="Current password"
            />
            <Button size="sm" onClick={enable} disabled={busy || !password}>
              {busy ? <Loader2 className="size-3.5 animate-spin" /> : "Confirm"}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setEnabling(false)} disabled={busy}>
              Cancel
            </Button>
          </div>
        ) : (
          <Button
            size="sm"
            className="bg-orange-600 text-white hover:bg-orange-700"
            onClick={() => setEnabling(true)}
          >
            Enable 2FA
          </Button>
        )}
      </div>
    </div>
  );
}

/** Landlord's own listings with their paid tier and a promote action. */
function ListingsTab({ onPromote }: { onPromote: (room: Room) => void }) {
  const { user } = useApp();
  // Server-side owner filter: the landlord dashboard only needs this owner's
  // listings, and a client-side filter over the first page of *all* rooms
  // would silently drop listings beyond page 1.
  const { data: rooms = [], isLoading } = useRooms(
    user?.id != null ? { owner: user.id } : undefined
  );

  const myRooms = rooms;

  if (isLoading) {
    return (
      <div className="py-15 text-center text-gray-600 dark:text-gray-400">
        Loading your listings…
      </div>
    );
  }

  return (
    <div>
      <div className="mb-5 flex items-center gap-2">
        <Megaphone className="size-5 text-orange-600" />
        <div>
          <h2 className="font-display text-lg font-bold text-foreground">My Listings</h2>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Manage your rooms and promote them to reach more tenants.
          </p>
        </div>
      </div>

      {myRooms.length === 0 ? (
        <div className="flex flex-col items-center px-5 py-15 text-center text-gray-600 dark:text-gray-400">
          <Megaphone className="mb-4 size-12" />
          <h3 className="mb-2 font-display text-lg font-bold text-foreground">No listings yet</h3>
          <p>Create a room listing to start renting it out.</p>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {myRooms.map((room) => (
            <div
              key={room.id}
              className="flex flex-col gap-3 rounded-2xl border border-gray-200 bg-card p-4 dark:border-gray-800 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="flex items-center gap-3">
                <img
                  src={room.img}
                  alt={room.name}
                  className="h-16 w-24 shrink-0 rounded-lg object-cover"
                />
                <div>
                  <div className="flex items-center gap-2 font-display text-sm font-bold text-foreground">
                    {room.name}
                    <TierBadge tier={room.tier} showFree />
                  </div>
                  <div className="mt-0.5 text-xs text-gray-600 dark:text-gray-400">
                    {room.area} • ৳{room.price.toLocaleString()}/mo •{" "}
                    {room.available ? "Available" : "Unavailable"}
                  </div>
                  {room.tierExpiresAt && room.tier !== "free" && (
                    <div className="mt-1 text-xs text-amber-600 dark:text-amber-400">
                      {room.tier === "premium" ? "Premium" : "Featured"} until{" "}
                      {new Date(room.tierExpiresAt).toLocaleDateString()}
                    </div>
                  )}
                </div>
              </div>
              <Button
                size="sm"
                className="shrink-0 bg-orange-600 text-white hover:bg-orange-700"
                onClick={() => onPromote(room)}
              >
                <Megaphone className="mr-1.5 size-3.5" />
                {room.tier === "free" ? "Promote" : "Upgrade"}
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** Fraud-alert tab: reports on the landlord's own listings (admin sees all). */
function FraudTab() {
  const { data: reports = [], isLoading } = useFraudReports();
  const scanRoom = useScanRoom();
  const review = useReviewFraudReport();
  const { user } = useApp();
  const isAdmin = user?.role === "admin";

  const severityClasses: Record<string, string> = {
    clean: "bg-emerald-500/10 text-emerald-500",
    low: "bg-yellow-500/10 text-yellow-500",
    medium: "bg-orange-500/10 text-orange-500",
    high: "bg-red-500/10 text-red-500",
  };
  const statusClasses: Record<string, string> = {
    open: "bg-red-500/10 text-red-500",
    reviewed: "bg-blue-500/10 text-blue-500",
    dismissed: "bg-gray-500/10 text-gray-500",
  };

  if (isLoading) {
    return (
      <div className="py-15 text-center text-gray-600 dark:text-gray-400">
        Loading fraud reports…
      </div>
    );
  }

  return (
    <div>
      <div className="mb-5 flex items-center gap-2">
        <ShieldAlert className="size-5 text-orange-600" />
        <div>
          <h2 className="font-display text-lg font-bold text-foreground">Fraud &amp; Safety</h2>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            {isAdmin
              ? "All listings flagged by the fraud detector."
              : "Auto-detected risk signals on your listings."}
          </p>
        </div>
      </div>

      {reports.length === 0 ? (
        <div className="flex flex-col items-center px-5 py-15 text-center text-gray-600 dark:text-gray-400">
          <ShieldCheck className="mb-4 size-12 text-emerald-500" />
          <h3 className="mb-2 font-display text-lg font-bold text-foreground">
            No flagged listings
          </h3>
          <p>Your listings passed the fraud scan. New rooms are checked automatically.</p>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {reports.map((report) => {
            const isScanning = scanRoom.isPending && scanRoom.variables === report.room.id;
            return (
              <div
                key={report.id}
                className="rounded-2xl border border-gray-200 bg-card p-5 dark:border-gray-800"
              >
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div className="flex items-center gap-3">
                    <img
                      src={report.room.img}
                      alt={report.room.name}
                      className="h-16 w-24 shrink-0 rounded-lg object-cover"
                    />
                    <div>
                      <div className="font-display text-sm font-bold text-foreground">
                        {report.room.name}
                      </div>
                      <div className="text-xs text-gray-600 dark:text-gray-400">
                        {report.room.area} • {report.room.type}
                      </div>
                      <div className="mt-1.5 flex flex-wrap gap-1.5">
                        <span
                          className={cn(
                            "inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold",
                            severityClasses[report.severity]
                          )}
                        >
                          {report.severityDisplay} risk · {report.score}/100
                        </span>
                        <span
                          className={cn(
                            "inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold",
                            statusClasses[report.status]
                          )}
                        >
                          {report.statusDisplay}
                        </span>
                      </div>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => scanRoom.mutate(report.room.id)}
                      disabled={isScanning}
                    >
                      {isScanning ? <Loader2 className="size-3.5 animate-spin" /> : "Re-scan"}
                    </Button>
                    {isAdmin && report.status === "open" && (
                      <>
                        <Button
                          size="sm"
                          onClick={() => review.mutate({ reportId: report.id, action: "reviewed" })}
                        >
                          Mark reviewed
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() =>
                            review.mutate({ reportId: report.id, action: "dismissed" })
                          }
                        >
                          Dismiss
                        </Button>
                      </>
                    )}
                  </div>
                </div>

                {report.signals.length > 0 && (
                  <div className="mt-4 flex flex-col gap-2 border-t border-gray-100 pt-4 dark:border-gray-800">
                    {report.signals.map((signal) => (
                      <div key={signal.id} className="flex items-start gap-2 text-sm">
                        <span
                          className={cn(
                            "mt-1 size-2 shrink-0 rounded-full",
                            signal.severity === "high"
                              ? "bg-red-500"
                              : signal.severity === "medium"
                                ? "bg-orange-500"
                                : "bg-yellow-500"
                          )}
                        />
                        <div>
                          <span className="font-semibold text-foreground">
                            {signal.detectorDisplay}:
                          </span>{" "}
                          <span className="text-gray-600 dark:text-gray-400">{signal.message}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
