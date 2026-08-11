import { useQuery } from "@tanstack/react-query";
import { Eye, Heart, TrendingDown, TrendingUp } from "lucide-react";
import roomService from "../../services/roomService";
import { cn } from "../../lib/utils";

/** Landlord listing insights — views, saves, bookings, price vs area (Phase 10). */
export default function LandlordInsights() {
  const { data: insights, isLoading } = useQuery({
    queryKey: ["room-insights"],
    queryFn: roomService.getInsights,
  });

  if (isLoading) {
    return <div className="py-8 text-sm text-gray-600 dark:text-gray-400">Loading insights…</div>;
  }
  if (!insights) return null;

  return (
    <div>
      <div className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div className="rounded-xl bg-gray-50 p-4 dark:bg-gray-800">
          <div className="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-400">
            <Eye className="size-3.5" /> Views (30d)
          </div>
          <div className="mt-1 font-display text-2xl font-bold text-foreground">
            {insights.summary.totalViews30d}
          </div>
        </div>
        <div className="rounded-xl bg-gray-50 p-4 dark:bg-gray-800">
          <div className="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-400">
            <Heart className="size-3.5" /> Wishlist saves
          </div>
          <div className="mt-1 font-display text-2xl font-bold text-foreground">
            {insights.summary.totalWishlists}
          </div>
        </div>
        <div className="rounded-xl bg-gray-50 p-4 dark:bg-gray-800">
          <div className="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-400">
            📦 Active listings
          </div>
          <div className="mt-1 font-display text-2xl font-bold text-foreground">
            {insights.summary.listingCount}
          </div>
        </div>
      </div>

      <div className="overflow-x-auto rounded-xl border border-gray-200 dark:border-gray-700">
        <table className="w-full min-w-[640px] text-left text-sm">
          <thead className="border-b border-gray-200 bg-gray-50 text-xs text-gray-600 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-400">
            <tr>
              <th className="px-4 py-3 font-semibold">Listing</th>
              <th className="px-4 py-3 font-semibold">Views 7d / 30d</th>
              <th className="px-4 py-3 font-semibold">Wishlists</th>
              <th className="px-4 py-3 font-semibold">Bookings</th>
              <th className="px-4 py-3 font-semibold">Price vs area</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
            {insights.rooms.map((room) => (
              <tr key={room.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                <td className="px-4 py-3">
                  <div className="font-semibold text-foreground">{room.title}</div>
                  <div className="text-xs text-gray-600 dark:text-gray-400">
                    {room.area} · ৳{room.price.toLocaleString()}/mo
                    {room.verified && (
                      <span className="ml-1.5 rounded-full bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-600 dark:text-emerald-400">
                        verified
                      </span>
                    )}
                  </div>
                </td>
                <td className="px-4 py-3">
                  {room.views7d} / {room.views30d}
                </td>
                <td className="px-4 py-3">{room.wishlistCount}</td>
                <td className="px-4 py-3">
                  {room.bookingApproved} approved
                  <span className="block text-xs text-gray-600 dark:text-gray-400">
                    {room.bookingRequests} requests
                  </span>
                </td>
                <td className="px-4 py-3">
                  {room.areaAvgPrice != null ? (
                    <span
                      className={cn(
                        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold",
                        (room.priceDeltaPct ?? 0) <= 0
                          ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                          : "bg-amber-500/10 text-amber-600 dark:text-amber-400"
                      )}
                    >
                      {(room.priceDeltaPct ?? 0) <= 0 ? (
                        <TrendingDown className="size-3" />
                      ) : (
                        <TrendingUp className="size-3" />
                      )}
                      {(room.priceDeltaPct ?? 0) > 0 ? "+" : ""}
                      {room.priceDeltaPct}% vs ৳{Math.round(room.areaAvgPrice).toLocaleString()}
                    </span>
                  ) : (
                    <span className="text-xs text-gray-600 dark:text-gray-400">
                      No market data yet
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-xs text-gray-600 dark:text-gray-400">
        Views count authenticated detail-page visits (deduplicated) — a lower bound on real traffic.
        Price deltas compare against the area/type market average.
      </p>
    </div>
  );
}
