/**
 * BookingListItem — one booking's row in the "bookings" tab.
 *
 * Deposit status is fetched per booking so the badge always reflects
 * the authoritative, live state rather than whatever was last cached
 * on the booking list.
 */

import { ShieldCheck } from "lucide-react";
import { useDepositStatus } from "../../hooks/usePayments";
import { Button } from "../../components/ui/button";
import type { Booking } from "../../types";
import { cn } from "../../lib/utils";

const statusClasses: Record<string, string> = {
  approved: "bg-emerald-500/10 text-emerald-500",
  pending: "bg-amber-500/10 text-amber-500",
  rejected: "bg-red-500/10 text-red-500",
  cancelled: "bg-gray-500/10 text-gray-500",
};

export default function BookingListItem({
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
          {booking.tenantTrustSignals && booking.tenantTrustSignals.completedBookings > 0 && (
            <span
              title="Approved bookings this tenant has completed on Rentora."
              className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-xs font-semibold text-emerald-600 dark:text-emerald-400"
            >
              ✓ {booking.tenantTrustSignals.completedBookings.toLocaleString()} completed booking
              {booking.tenantTrustSignals.completedBookings > 1 ? "s" : ""}
            </span>
          )}
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
