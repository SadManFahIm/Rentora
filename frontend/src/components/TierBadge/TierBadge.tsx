import { Crown, Flame, Sparkles } from "lucide-react";
import type { ListingTier } from "../../types";
import { cn } from "../../lib/utils";

const tierConfig: Record<ListingTier, { label: string; icon: typeof Sparkles; classes: string }> = {
  premium: {
    label: "Premium",
    icon: Crown,
    classes: "bg-gradient-to-r from-amber-400 via-orange-500 to-pink-500 text-white shadow-sm",
  },
  featured: {
    label: "Featured",
    icon: Flame,
    classes: "bg-orange-600 text-white shadow-sm",
  },
  free: {
    label: "Free",
    icon: Sparkles,
    classes: "bg-gray-200 text-gray-600 dark:bg-gray-700 dark:text-gray-300",
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
        "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[0.7rem] font-bold tracking-wide",
        config.classes,
        className
      )}
    >
      <Icon className="size-3" />
      {config.label}
    </span>
  );
}
