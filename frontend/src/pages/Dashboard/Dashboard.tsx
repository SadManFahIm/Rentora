import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Heart, Loader2 } from "lucide-react";
import { useDashboard } from "../../hooks/useDashboard";
import { useBookings } from "../../hooks/useBookings";
import { useDownloadReceipt, usePaymentHistory, usePaymentSummary } from "../../hooks/usePayments";
import { wishlistService } from "../../services/wishlistService";
import roomService from "../../services/roomService";
import { useApp } from "../../context/AppContext";
import FraudTab from "../../components/FraudTab/FraudTab";
import AdminFraudPanel from "../../components/AdminFraudPanel/AdminFraudPanel";
import AdminReportsPanel from "../../components/AdminReportsPanel/AdminReportsPanel";
import AdminModerationPanel from "../../components/AdminModerationPanel/AdminModerationPanel";
import AdminDisputesPanel from "../../components/AdminDisputesPanel/AdminDisputesPanel";
import DisputesTab from "../../components/DisputesTab/DisputesTab";
import AdminTrustCenter from "../../components/AdminTrustCenter/AdminTrustCenter";
import LandlordInsights from "../../components/LandlordInsights/LandlordInsights";
import LandlordAiWidget from "../../components/LandlordAiWidget/LandlordAiWidget";
import PushNotificationCard from "../../components/PushNotificationCard/PushNotificationCard";
import ReferralCard from "../../components/ReferralCard/ReferralCard";
import WishlistShareButton from "../../components/WishlistShareButton/WishlistShareButton";
import KycCard from "../../components/KycCard/KycCard";
import TenantKycCard from "../../components/TenantKycCard/TenantKycCard";
import AdminKycPanel from "../../components/AdminKycPanel/AdminKycPanel";
import SubscriptionPanel from "../../components/SubscriptionPanel/SubscriptionPanel";
import BrokerPanel from "../../components/BrokerPanel/BrokerPanel";
import CorporatePanel from "../../components/CorporatePanel/CorporatePanel";
import MarketplacePanel from "../../components/MarketplacePanel/MarketplacePanel";
import InsurancePanel from "../../components/InsurancePanel/InsurancePanel";
import AdminRevenuePanel from "../../components/AdminRevenuePanel/AdminRevenuePanel";
import AdminAiPanel from "../../components/AdminAiPanel/AdminAiPanel";
import AutopilotPanel from "../../components/AutopilotPanel/AutopilotPanel";
import RoomCard from "../../components/RoomCard/RoomCard";
import RoomModal from "../../components/RoomModal/RoomModal";
import RoomForm from "../../components/RoomForm/RoomForm";
import PromoteModal from "../../components/PromoteModal/PromoteModal";
import PaymentMethodModal, {
  type PaymentRequest,
} from "../../components/PaymentMethodModal/PaymentMethodModal";
import { Button } from "../../components/ui/button";
import { Skeleton } from "../../components/ui/skeleton";
import { Input } from "../../components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../../components/ui/select";
import type { Booking, PaymentStatus, Room } from "../../types";
import { cn } from "../../lib/utils";

// Extracted tab components
import BookingListItem from "./BookingListItem";
import TwoFactorCard from "./TwoFactorCard";
import ListingsTab from "./ListingsTab";

type DashboardTab =
  | "overview"
  | "listings"
  | "bookings"
  | "payments"
  | "wishlist"
  | "fraud"
  | "kyc"
  | "reports"
  | "moderation"
  | "disputes"
  | "trust"
  | "insights"
  | "monetization"
  | "broker"
  | "corporate"
  | "revenue"
  | "ai";
const TABS: DashboardTab[] = [
  "overview",
  "listings",
  "bookings",
  "payments",
  "wishlist",
  "fraud",
  "kyc",
  "reports",
  "moderation",
  "disputes",
  "trust",
  "insights",
  "monetization",
  "broker",
  "corporate",
  "revenue",
  "ai",
];

interface StatCard {
  icon: string;
  label: string;
  value: string;
  change: string;
}

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

export default function Dashboard() {
  const queryClient = useQueryClient();
  const { user } = useApp();
  const [searchParams] = useSearchParams();
  const requestedTab = searchParams.get("tab");
  const [activeTab, setActiveTab] = useState<DashboardTab>(
    (TABS as string[]).includes(requestedTab ?? "") ? (requestedTab as DashboardTab) : "overview"
  );
  const [selectedRoom, setSelectedRoom] = useState<Room | null>(null);
  const [showRoomForm, setShowRoomForm] = useState(false);
  const [payRequest, setPayRequest] = useState<PaymentRequest | null>(null);
  const [promoteRoom, setPromoteRoom] = useState<Room | null>(null);

  const [statusFilter, setStatusFilter] = useState<PaymentStatus | "all">("all");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  // The KYC review tab is admin-only (mirrors the backend's staff-or-admin
  // check); the KYC upload card is for everyone else. Listing insights are
  // for landlords (and admins see every listing).
  const isAdmin = user?.role === "admin" || user?.isStaff === true;
  const isLandlord = isAdmin || user?.role === "landlord";
  const visibleTabs = TABS.filter((t) => {
    if (t === "kyc" || t === "reports" || t === "moderation" || t === "trust") return isAdmin;
    if (t === "revenue") return isAdmin;
    if (t === "ai") return isAdmin;
    if (t === "insights") return isLandlord;
    return true;
  });

  const { data: stats, isLoading: statsLoading } = useDashboard();
  const { data: bookings = [], isLoading: bookingsLoading } = useBookings();
  const { data: wishlistedRooms = [], isLoading: wishlistLoading } = useQuery<Room[]>({
    queryKey: ["wishlist", "rooms"],
    queryFn: () => wishlistService.getWishlist(),
  });

  // Landlord listing-quality summary (avg of the 0-100 completeness scores).
  const { data: insights } = useQuery({
    queryKey: ["room-insights"],
    queryFn: roomService.getInsights,
    enabled: isLandlord,
  });
  const qualityScores = (insights?.rooms ?? [])
    .map((r) => r.listingQuality?.score)
    .filter((s): s is number => s != null);
  const avgQuality =
    qualityScores.length > 0
      ? Math.round(qualityScores.reduce((a, b) => a + b, 0) / qualityScores.length)
      : null;

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

  const qualityCard: StatCard | null =
    avgQuality != null
      ? {
          icon: "✨",
          label: "Avg Listing Quality",
          value: `${avgQuality} / 100`,
          change: avgQuality >= 75 ? "Strong listings" : "Improve in Insights",
        }
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
          onClick={() => setShowRoomForm(true)}
        >
          + List a Room
        </Button>
      </div>

      <div className="mb-6 flex w-fit gap-1 rounded-xl bg-gray-50 p-1 dark:bg-gray-800">
        {visibleTabs.map((t) => (
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

          {/* Phase 10 — invite friends + browser notifications */}
          <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <ReferralCard />
            <PushNotificationCard />
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
                {qualityCard && (
                  <div
                    className={cn(
                      "rounded-2xl border border-gray-200 bg-card p-5 dark:border-gray-800",
                      qualityCard.change !== "Strong listings" &&
                        "border-amber-500/40 dark:border-amber-500/30"
                    )}
                  >
                    <div className="mb-2.5 text-2xl">{qualityCard.icon}</div>
                    <h3 className="font-display text-2xl font-bold text-foreground">
                      {qualityCard.value}
                    </h3>
                    <p className="text-sm text-gray-600 dark:text-gray-400">{qualityCard.label}</p>
                    <div className="text-sm font-semibold text-emerald-500">
                      {qualityCard.change}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {!isAdmin && (
            <div className="mb-6">
              {/* Two-sided trust (Phase 12): landlords verify identity to get
                  the listing badge; tenants verify to get the verified-tenant
                  badge landlords see when they inquire or book. */}
              {user?.role === "tenant" ? <TenantKycCard /> : <KycCard />}
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

      {activeTab === "wishlist" && (
          <div className="mb-4 flex justify-end">
            <WishlistShareButton />
          </div>
        ) &&
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

      {activeTab === "fraud" && (isAdmin ? <AdminFraudPanel /> : <FraudTab />)}

      {activeTab === "kyc" && isAdmin && <AdminKycPanel />}

      {activeTab === "reports" && isAdmin && <AdminReportsPanel />}

      {activeTab === "moderation" && isAdmin && <AdminModerationPanel />}

      {activeTab === "disputes" && (isAdmin ? <AdminDisputesPanel /> : <DisputesTab />)}

      {activeTab === "trust" && isAdmin && <AdminTrustCenter />}

      {activeTab === "insights" && isLandlord && (
        <>
          <LandlordInsights />
          <div className="mt-6">
            <LandlordAiWidget />
          </div>
          <div className="mt-6">
            <AutopilotPanel />
          </div>
        </>
      )}

      {activeTab === "monetization" && (
        <div className="flex flex-col gap-10">
          <SubscriptionPanel />
          <hr className="border-gray-200 dark:border-gray-800" />
          <MarketplacePanel />
          <hr className="border-gray-200 dark:border-gray-800" />
          <InsurancePanel />
        </div>
      )}

      {activeTab === "broker" && <BrokerPanel />}

      {activeTab === "corporate" && <CorporatePanel />}

      {activeTab === "revenue" && isAdmin && <AdminRevenuePanel />}

      {activeTab === "ai" && isAdmin && <AdminAiPanel />}

      {selectedRoom && <RoomModal room={selectedRoom} onClose={() => setSelectedRoom(null)} />}

      <RoomForm open={showRoomForm} onClose={() => setShowRoomForm(false)} />
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
