import { Crown, Flame, Sparkles } from "lucide-react";
import type { ListingTier } from "../../types";
import { cn } from "../../lib/utils";

const tierConfig: Record<ListingTier, { label: string; icon: typeof Sparkles; classes: string }> = {
  premium: {
    label: "Premium",
    icon: Crown,
    classes: "bg-warning text-warning-foreground border border-warning/30 shadow-xs",
  },
  featured: {
    label: "Featured",
    icon: Flame,
    classes: "bg-brand text-brand-foreground shadow-xs",
  },
  free: {
    label: "Free",
    icon: Sparkles,
    classes: "bg-surface-subtle text-muted-foreground border border-border",
  },
};

/** Small pill marking a listing's paid tier. Renders nothing for free rooms
 * unless `showFree` is set (used in the landlord's listings manager). */
export default function TierBadge({
  tier,
  showFree = false,
  className,
}: {
  tier: ListingTier;
  showFree?: boolean;
  className?: string;
}) {
  if (tier === "free" && !showFree) return null;
  const config = tierConfig[tier];
  const Icon = config.icon;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-sm px-2 py-0.5 text-[0.7rem] font-bold tracking-wide",
        config.classes,
        className
      )}
    >
      <Icon className="size-3" />
      {config.label}
    </span>
  );
}
