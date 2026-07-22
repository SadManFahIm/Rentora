import { Star, MapPin, Heart, ShieldCheck } from "lucide-react";
import { useWishlistStore } from "../../stores/wishlistStore";
import type { Room, RoomType } from "../../types";
import { Card, CardContent } from "../ui/card";
import { Badge } from "../ui/badge";
import { cn } from "../../lib/utils";

interface RoomCardProps {
  room: Room;
  onClick: (room: Room) => void;
}

const typeClasses: Record<RoomType, string> = {
  Single: "border-blue-500/30 bg-blue-500/10 text-blue-600 dark:text-blue-400",
  Shared: "border-violet-500/30 bg-violet-500/10 text-violet-600 dark:text-violet-400",
  Studio: "border-brand/30 bg-brand/10 text-brand",
};

export default function RoomCard({ room, onClick }: RoomCardProps) {
  const wishlist = useWishlistStore((s) => s.wishlist);
  const toggleWishlist = useWishlistStore((s) => s.toggleWishlist);
  const isWishlisted = wishlist.includes(room.id);

  return (
    <Card
      className="group cursor-pointer gap-0 overflow-hidden py-0! transition-all duration-300 hover:-translate-y-1 hover:shadow-lg"
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
          variant={room.available ? "brand" : "secondary"}
          className="absolute left-3 top-3"
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
            className={cn("size-4", isWishlisted ? "fill-brand text-brand" : "text-neutral-500")}
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
            <div className="mt-1 flex items-center gap-1 text-sm text-muted-foreground">
              <MapPin className="size-3.5 shrink-0" /> {room.area}
            </div>
          </div>
          <div className="shrink-0 text-right">
            <div className="font-display text-lg font-extrabold text-taka">
              ৳{room.price.toLocaleString()}
              <sub className="text-xs font-medium text-muted-foreground">/mo</sub>
            </div>
            <Badge variant="outline" className={cn("mt-1", typeClasses[room.type])}>
              {room.type}
            </Badge>
          </div>
        </div>

        {/* Amenities */}
        <div className="mb-3 flex flex-wrap gap-1.5">
          {room.amenities.slice(0, 3).map((a) => (
            <span key={a} className="rounded-md bg-muted px-2.5 py-1 text-xs text-muted-foreground">
              {a}
            </span>
          ))}
          {room.amenities.length > 3 && (
            <span className="rounded-md bg-muted px-2.5 py-1 text-xs text-muted-foreground">
              +{room.amenities.length - 3}
            </span>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-border pt-3">
          <div className="flex items-center gap-1 text-sm font-semibold text-foreground">
            <Star className="size-3.5 fill-amber-500 text-amber-500" /> {room.rating}
            <span className="font-normal text-muted-foreground">({room.reviews})</span>
          </div>
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <div className="flex h-7 w-7 items-center justify-center rounded-full bg-linear-to-br from-brand to-brand-dark text-[0.65rem] font-bold text-white">
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
