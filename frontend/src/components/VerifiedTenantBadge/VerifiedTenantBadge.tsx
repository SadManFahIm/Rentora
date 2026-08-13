import { BadgeCheck, ShieldOff } from "lucide-react";
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
  className?: string;
}

/**
 * The Phase 12 "Identity Verified" tenant badge.
 *
 * Trust indicators must be informative, not misleading: this badge only ever
 * claims identity verification passed — it never implies "safe tenant",
 * "guaranteed tenant", or "creditworthy". The tooltip says exactly what it
 * means: "Identity verified by Rentora."
 */
export default function VerifiedTenantBadge({
  verified,
  showUnverified = false,
  className,
}: VerifiedTenantBadgeProps) {
  if (verified) {
    return (
      <Badge
        variant="brand"
        title="Identity verified by Rentora."
        aria-label="Identity verified tenant"
        className={cn("gap-1 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400", className)}
      >
        <BadgeCheck className="size-3" aria-hidden />
        Identity Verified
      </Badge>
    );
  }

  if (!showUnverified) return null;

  return (
    <Badge
      variant="outline"
      title="Identity verification pending or not started."
      aria-label="Tenant not verified"
      className={cn("gap-1 text-gray-500", className)}
    >
      <ShieldOff className="size-3" aria-hidden />
      Not verified
    </Badge>
  );
}
