import { Star, ShieldCheck, MessageCircle, CalendarCheck } from "lucide-react";
import type { Room } from "../../types";
import { Dialog, DialogContent, DialogTitle } from "../ui/dialog";
import { Button } from "../ui/button";
import { VisuallyHidden } from "../ui/visually-hidden";

const amenityEmoji: Record<string, string> = {
  WiFi: "📶",
  AC: "❄️",
  "Attached Bath": "🚿",
  Furnished: "🛋️",
  Gym: "💪",
  Parking: "🚗",
};

interface RoomModalProps {
  room: Room | null;
  onClose: () => void;
}

export default function RoomModal({ room, onClose }: RoomModalProps) {
  return (
    <Dialog open={!!room} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90vh] max-w-3xl gap-0 overflow-y-auto rounded-xl p-0" showCloseButton>
        {room && (
          <>
            <VisuallyHidden>
              <DialogTitle>{room.name}</DialogTitle>
            </VisuallyHidden>
            <img src={room.img} alt={room.name} className="h-75 w-full object-cover" />
            <div className="p-7">
              {/* Header */}
              <div className="mb-4 flex items-start justify-between gap-4">
                <div>
                  <h2 className="font-display text-2xl font-bold text-foreground">{room.name}</h2>
                  <div className="mt-1 flex flex-wrap items-center gap-3">
                    <span className="flex items-center gap-1 text-sm font-semibold text-amber-500">
                      <Star className="size-4 fill-amber-500" /> {room.rating}
                    </span>
                    <span className="text-sm text-gray-600 dark:text-gray-400">({room.reviews} reviews)</span>
                    {room.verified && (
                      <span className="flex items-center gap-1 text-xs font-semibold text-emerald-500">
                        <ShieldCheck className="size-3.5" /> KYC Verified
                      </span>
                    )}
                  </div>
                </div>
              </div>

              {/* Price */}
              <div className="font-display text-3xl font-bold text-orange-600">
                ৳{room.price.toLocaleString()}
                <span className="ml-1 text-base font-normal text-gray-600 dark:text-gray-400">/month</span>
              </div>
              <div className="mt-3 rounded-r-xl border-l-4 border-orange-600 bg-orange-50 px-4 py-3 text-sm text-gray-600 dark:bg-orange-950/20 dark:text-gray-400">
                🤖 AI Price Insight: This listing is <strong className="text-foreground">8% below market average</strong> for {room.area}. Great deal!
              </div>

              {/* Info Grid */}
              <div className="my-5 grid grid-cols-2 gap-3 sm:grid-cols-3">
                <div className="rounded-xl bg-gray-50 p-3.5 text-center dark:bg-gray-800">
                  <strong className="block font-display font-bold text-foreground">{room.type}</strong>
                  <span className="text-xs text-gray-600 dark:text-gray-400">Room Type</span>
                </div>
                <div className="rounded-xl bg-gray-50 p-3.5 text-center dark:bg-gray-800">
                  <strong className="block font-display font-bold text-foreground">{room.size} sqft</strong>
                  <span className="text-xs text-gray-600 dark:text-gray-400">Size</span>
                </div>
                <div className="rounded-xl bg-gray-50 p-3.5 text-center dark:bg-gray-800">
                  <strong className="block font-display font-bold text-foreground">{room.gender}</strong>
                  <span className="text-xs text-gray-600 dark:text-gray-400">Gender Pref.</span>
                </div>
              </div>

              {/* Description */}
              <p className="mb-4 text-sm leading-relaxed text-gray-600 dark:text-gray-400">{room.description}</p>

              {/* Amenities */}
              <div className="my-4 flex flex-wrap gap-2">
                {room.amenities.map((a) => (
                  <span
                    key={a}
                    className="flex items-center gap-1.5 rounded-lg bg-gray-50 px-4 py-2 text-sm text-foreground dark:bg-gray-800"
                  >
                    {amenityEmoji[a] || "✓"} {a}
                  </span>
                ))}
              </div>

              {/* Owner */}
              <div className="mt-2 flex items-center gap-3 rounded-xl bg-gray-50 p-4 dark:bg-gray-800">
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-orange-600 text-sm font-bold text-white">
                  {room.ownerAvatar}
                </div>
                <div>
                  <div className="text-sm font-bold text-foreground">{room.owner}</div>
                  {room.verified && (
                    <span className="flex items-center gap-1 text-xs font-semibold text-emerald-500">
                      <ShieldCheck className="size-3.5" /> NID Verified
                    </span>
                  )}
                </div>
              </div>

              {/* Actions */}
              <div className="mt-6 flex gap-3">
                <Button variant="outline" className="flex-1" size="lg">
                  <MessageCircle className="size-4" /> Message Owner
                </Button>
                <Button className="flex-1 bg-orange-600 text-white hover:bg-orange-700" size="lg">
                  <CalendarCheck className="size-4" /> Book Now
                </Button>
              </div>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
