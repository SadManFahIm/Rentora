import { useTranslation } from "react-i18next";
import { BadgeCheck, CalendarCheck, ShieldOff } from "lucide-react";
import { cn } from "../../lib/utils";
import { Badge } from "../ui/badge";

interface VerifiedTenantBadgeProps {
  /**
   * Coarse trust state exposed to *other* users (landlords): true means the
   * tenant's identity verification passed. False or undefined means the
   * landlord only ever sees nothing (or the muted "Not verified" chip when
   * `showUnverified` is set) — never the document or verification details.
   */
  verified?: boolean;
  /** Render a muted "Not verified" chip when `verified` is false. */
  showUnverified?: boolean;
  /**
   * Behavioral trust signal (Tier 3): approved bookings this tenant has
   * actually completed on Rentora (deposit refunded or stay ended). Shown as
   * a separate transparent chip next to identity — it never inflates the
   * identity claim, it's a real platform fact.
   */
  completedBookings?: number;
  className?: string;
}

/**
 * The Phase 12 "Identity Verified" tenant badge, extended with the Tier-3
 * behavioral signal.
 *
 * Trust indicators must be informative, not misleading: the badge only ever
 * claims identity verification passed — it never implies "safe tenant",
 * "guaranteed tenant", or "creditworthy". The tooltip says exactly what it
 * means: "Identity verified by Rentora." Completed bookings are a separate,
 * equally precise claim backed by real booking data.
 */
export default function VerifiedTenantBadge({
  verified,
  showUnverified = false,
  completedBookings = 0,
  className,
}: VerifiedTenantBadgeProps) {
  const { t } = useTranslation();

  if (verified) {
    return (
      <span className={cn("inline-flex items-center gap-1.5", className)}>
        <Badge
          variant="brand"
          title={t("trust.identityTooltip")}
          aria-label={t("trust.identityVerifiedAria")}
          className="gap-1 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
        >
          <BadgeCheck className="size-3" aria-hidden />
          {t("trust.identityVerified")}
        </Badge>
        {completedBookings > 0 && (
          <Badge
            variant="outline"
            title={t("trust.completedBookingsTooltip")}
            aria-label={t("trust.completedBookings", { count: completedBookings })}
            className="gap-1 text-emerald-700 dark:text-emerald-300"
          >
            <CalendarCheck className="size-3" aria-hidden />
            {t("trust.completedBookings", { count: completedBookings })}
          </Badge>
        )}
      </span>
    );
  }

  if (!showUnverified) return null;

  return (
    <Badge
      variant="outline"
      title={t("trust.pendingTooltip")}
      aria-label={t("trust.notVerifiedAria")}
      className={cn("gap-1 text-gray-500", className)}
    >
      <ShieldOff className="size-3" aria-hidden />
      {t("trust.notVerified")}
    </Badge>
  );
}
