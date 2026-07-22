import { Star, MapPin, Heart, ShieldCheck } from "lucide-react";
import { useWishlistStore } from "../../stores/wishlistStore";
import type { Room } from "../../types";
import { Card, CardContent } from "../ui/card";
import { Badge } from "../ui/badge";
import { cn } from "../../lib/utils";

interface RoomCardProps {
  room: Room;
  onClick: (room: Room) => void;
}

export default function RoomCard({ room, onClick }: RoomCardProps) {
  const wishlist = useWishlistStore((s) => s.wishlist);
  const toggleWishlist = useWishlistStore((s) => s.toggleWishlist);
  const isWishlisted = wishlist.includes(room.id);

  return (
    <Card
      className="group cursor-pointer gap-0 overflow-hidden rounded-xl border-gray-200 py-0! transition-all duration-300 hover:-translate-y-1 hover:shadow-lg dark:border-gray-800"
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
          {room.available ? room.type : "Unavailable"}
        </Badge>
        <button
          className="absolute right-3 top-3 flex h-9 w-9 items-center justify-center rounded-full bg-white/90 shadow-sm transition-transform hover:scale-110"
          onClick={(e) => {
            e.stopPropagation();
            toggleWishlist(room.id);
          }}
          aria-label={isWishlisted ? "Remove from wishlist" : "Add to wishlist"}
        >
          <Heart
            className={cn("size-4", isWishlisted ? "fill-orange-600 text-orange-600" : "text-neutral-500")}
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
              <sub className="text-xs font-medium text-gray-500">/mo</sub>
            </div>
            <Badge className="mt-1 border-transparent bg-orange-600 text-white">{room.type}</Badge>
          </div>
        </div>

        {/* Amenities */}
        <div className="mb-3 flex flex-wrap gap-1.5">
          {room.amenities.slice(0, 3).map((a) => (
            <span key={a} className="rounded-md bg-gray-50 px-2.5 py-1 text-xs text-gray-600 dark:bg-gray-800 dark:text-gray-400">
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
            {room.verified && <ShieldCheck className="size-3.5 text-emerald-500" />}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
