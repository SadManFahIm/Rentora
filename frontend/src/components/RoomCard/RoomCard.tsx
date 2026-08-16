import { Star, MapPin, Heart, ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useWishlistStore } from "../../stores/wishlistStore";
import type { Room } from "../../types";
import { Card, CardContent } from "../ui/card";
import { Badge } from "../ui/badge";
import TierBadge from "../TierBadge/TierBadge";
import { cn } from "../../lib/utils";

interface RoomCardProps {
  room: Room;
  onClick: (room: Room) => void;
}

export default function RoomCard({ room, onClick }: RoomCardProps) {
  const { t } = useTranslation();
  const wishlist = useWishlistStore((s) => s.wishlist);
  const toggleWishlist = useWishlistStore((s) => s.toggleWishlist);
  const isWishlisted = wishlist.includes(room.id);

  const isPremium = room.tier === "premium";
  const isFeatured = room.tier === "featured";

  return (
    <Card
      className={cn(
        "group cursor-pointer gap-0 overflow-hidden rounded-xl py-0! transition-all duration-300 hover:-translate-y-1 hover:shadow-lg",
        isPremium
          ? "border-amber-400 shadow-md ring-1 ring-amber-400/60 dark:border-amber-500/70"
          : isFeatured
            ? "border-orange-300 dark:border-orange-500/50"
            : "border-gray-200 dark:border-gray-800"
      )}
      onClick={() => onClick(room)}
    >
      {/* Image */}
      <div className="relative h-50 overflow-hidden">
        <img
          src={room.img}
          alt={room.name}
          loading="lazy"
          className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
        />
        <Badge
          className={cn(
            "absolute left-3 top-3 border-transparent",
            room.available ? "bg-orange-600 text-white" : "bg-gray-500 text-white"
          )}
        >
          {room.available ? room.type : t("roomCard.unavailable")}
        </Badge>
        <div className="absolute left-3 top-3 flex flex-col items-start gap-1.5">
          <TierBadge tier={room.tier} />
        </div>
        <button
          className="absolute right-3 top-3 flex h-9 w-9 items-center justify-center rounded-full bg-white/90 shadow-sm transition-transform hover:scale-110"
          onClick={(e) => {
            e.stopPropagation();
            toggleWishlist(room.id);
          }}
          aria-label={isWishlisted ? t("roomCard.removeFromWishlist") : t("roomCard.addToWishlist")}
        >
          <Heart
            className={cn(
              "size-4",
              isWishlisted ? "fill-orange-600 text-orange-600" : "text-neutral-500"
            )}
          />
        </button>
      </div>

      {/* Body */}
      <CardContent className="px-4 py-4">
        <div className="mb-2 flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="truncate font-display text-base font-bold leading-tight text-foreground">
              {room.name}
            </div>
            <div className="mt-1 flex items-center gap-1 text-sm text-gray-600 dark:text-gray-400">
              <MapPin className="size-3.5 shrink-0" /> {room.area}
            </div>
          </div>
          <div className="shrink-0 text-right">
            <div className="font-display text-lg font-bold text-orange-600">
              ৳{room.price.toLocaleString()}
              <sub className="text-xs font-medium text-gray-500">{t("roomCard.perMonth")}</sub>
            </div>
            {room.priceAnomaly && (
              <span
                className={cn(
                  "mt-1 inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-[0.65rem] font-semibold leading-none",
                  room.priceAnomaly.direction === "above_market"
                    ? "bg-amber-500/10 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400"
                    : "bg-emerald-500/10 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400"
                )}
                title="Compared with the estimated market price for similar listings."
              >
                {room.priceAnomaly.direction === "above_market" ? "↑" : "↓"}{" "}
                {room.priceAnomaly.badge}
              </span>
            )}
            <Badge className="mt-1 border-transparent bg-orange-600 text-white">{room.type}</Badge>
          </div>
        </div>

        {/* Amenities */}
        <div className="mb-3 flex flex-wrap gap-1.5">
          {room.amenities.slice(0, 3).map((a) => (
            <span
              key={a}
              className="rounded-md bg-gray-50 px-2.5 py-1 text-xs text-gray-600 dark:bg-gray-800 dark:text-gray-400"
            >
              {a}
            </span>
          ))}
          {room.amenities.length > 3 && (
            <span className="rounded-md bg-gray-50 px-2.5 py-1 text-xs text-gray-600 dark:bg-gray-800 dark:text-gray-400">
              +{room.amenities.length - 3}
            </span>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-gray-200 pt-3 dark:border-gray-800">
          <div className="flex items-center gap-1 text-sm font-semibold text-foreground">
            <Star className="size-3.5 fill-amber-500 text-amber-500" /> {room.rating}
            <span className="font-normal text-gray-600 dark:text-gray-400">({room.reviews})</span>
          </div>
          <div className="flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-400">
            <div className="flex h-7 w-7 items-center justify-center rounded-full bg-orange-600 text-[0.65rem] font-bold text-white">
              {room.ownerAvatar}
            </div>
            {room.owner}
            {room.verified && (
              <span
                className="inline-flex items-center gap-0.5 rounded-full bg-emerald-500/10 px-1.5 py-0.5 text-[0.65rem] font-semibold text-emerald-600 dark:text-emerald-400"
                title="Verified landlord — identity documents approved"
              >
                <ShieldCheck className="size-3" />
                Verified
              </span>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
