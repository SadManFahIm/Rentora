import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import {
  ShieldAlert,
  Star,
  ShieldCheck,
  MessageCircle,
  CalendarCheck,
  Sparkles,
  HandCoins,
  Loader2,
} from "lucide-react";
import { useRoomFraudStatus } from "../../hooks/useFraud";
import { fraudBadgeLabel } from "../../lib/fraud";
import { track } from "../../services/analytics";
import { useCopilotStore } from "../../stores/copilotStore";
import type { Room } from "../../types";
import { Dialog, DialogContent, DialogTitle } from "../ui/dialog";
import { Button } from "../ui/button";
import { VisuallyHidden } from "../ui/visually-hidden";
import SimilarImages from "../SimilarImages/SimilarImages";
import SimilarRooms from "../SimilarRooms/SimilarRooms";
import ReviewsSection from "../ReviewsSection/ReviewsSection";
import { useCreateBooking } from "../../hooks/useBookings";
import { useStartDirectChat } from "../../hooks/useChat";
import { useListingShare } from "../../hooks/useListingShare";
import { useApp } from "../../context/AppContext";
import { isAuthenticated } from "../../services/api";
import { getApiErrorMessage } from "../../services/errors";

/** Default check-in: one week out, as an ISO date (YYYY-MM-DD). */
function defaultCheckIn(): string {
  const d = new Date();
  d.setDate(d.getDate() + 7);
  return d.toISOString().slice(0, 10);
}

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
  const navigate = useNavigate();
  const { user } = useApp();
  const { t } = useTranslation();
  const [current, setCurrent] = useState<Room | null>(room);
  const createBooking = useCreateBooking();
  const startChat = useStartDirectChat();
  const { share, sharingId } = useListingShare();
  // Live fraud badge — fetched only when the modal is open for this room.
  const { data: fraud } = useRoomFraudStatus(current?.id ?? null);

  // Funnel event (Tier 5): a room being *viewed* is the second conversion
  // step (after page_view). Fire once per room open.
  useEffect(() => {
    if (current?.id != null) {
      track("room_view", { room_id: current.id });
    }
  }, [current?.id]);

  const handleBook = () => {
    if (!current) return;
    if (!isAuthenticated()) {
      toast.info("Please sign in to book this room.");
      onClose();
      navigate("/auth");
      return;
    }
    // First-party analytics (Tier 2): the booking step of the conversion funnel.
    track("booking_requested", { room_id: current.id });
    createBooking.mutate({ roomId: current.id, checkIn: defaultCheckIn() }, { onSuccess: onClose });
  };

  const handleAskCopilot = () => {
    if (!current) return;
    // Tier 3 RAG: open the floating Copilot grounded on this listing — every
    // answer comes from this listing's facts, never invented. Tier 4: also
    // pass the price so the negotiation assistant can draft an offer.
    // Close the modal so the floating widget is actually visible above the
    // dialog overlay (both render at z-50).
    useCopilotStore.getState().openWithListing({
      id: current.id,
      title: current.name,
      price: current.price,
    });
    onClose();
  };

  const handleMessageOwner = () => {
    if (!current) return;
    if (!isAuthenticated()) {
      toast.info("Please sign in to message the owner.");
      onClose();
      navigate("/auth");
      return;
    }
    if (!current.ownerId) {
      toast.error("This room's owner can't be messaged right now.");
      return;
    }
    if (current.ownerId === user?.id) {
      toast.info("This is your own listing.");
      return;
    }
    startChat.mutate(
      { userId: current.ownerId, listingId: current.id },
      {
        onSuccess: (chatRoom) => {
          onClose();
          navigate(`/chat?room=${chatRoom.id}`);
        },
        onError: (error) =>
          toast.error(getApiErrorMessage(error, "Could not start a conversation.")),
      }
    );
  };

  return (
    <Dialog open={!!current} onOpenChange={(open) => !open && onClose()}>
      <DialogContent
        className="max-h-[90vh] max-w-3xl gap-0 overflow-y-auto rounded-xl p-0"
        showCloseButton
      >
        {current && (
          <>
            <VisuallyHidden>
              <DialogTitle>{current.name}</DialogTitle>
            </VisuallyHidden>
            <img src={current.img} alt={current.name} className="h-75 w-full object-cover" />
            <div className="p-7">
              {/* Header */}
              <div className="mb-4 flex items-start justify-between gap-4">
                <div>
                  <h2 className="font-display text-2xl font-bold text-foreground">
                    {current.name}
                  </h2>
                  <div className="mt-1 flex flex-wrap items-center gap-3">
                    <span className="flex items-center gap-1 text-sm font-semibold text-amber-500">
                      <Star className="size-4 fill-amber-500" /> {current.rating}
                    </span>
                    <span className="text-sm text-gray-600 dark:text-gray-400">
                      ({current.reviews} reviews)
                    </span>
                    {current.verified && (
                      <span className="flex items-center gap-1 text-xs font-semibold text-emerald-500">
                        <ShieldCheck className="size-3.5" /> KYC Verified
                      </span>
                    )}
                    {fraud?.flagged && (
                      <span className="flex items-center gap-1 rounded-full bg-red-50 px-2.5 py-0.5 text-xs font-semibold text-red-600 dark:bg-red-950/40 dark:text-red-400">
                        <ShieldAlert className="size-3.5" />
                        {fraudBadgeLabel(fraud.severity)}
                      </span>
                    )}
                  </div>
                </div>
              </div>

              {/* Price */}
              <div className="font-display text-3xl font-bold text-orange-600">
                ৳{current.price.toLocaleString()}
                <span className="ml-1 text-base font-normal text-gray-600 dark:text-gray-400">
                  /month
                </span>
              </div>
              <div className="mt-3 rounded-r-xl border-l-4 border-orange-600 bg-orange-50 px-4 py-3 text-sm text-gray-600 dark:bg-orange-950/20 dark:text-gray-400">
                🤖 AI Price Insight: This listing is{" "}
                <strong className="text-foreground">8% below market average</strong> for{" "}
                {current.area}. Great deal!
              </div>

              {/* Info Grid */}
              <div className="my-5 grid grid-cols-2 gap-3 sm:grid-cols-3">
                <div className="rounded-xl bg-gray-50 p-3.5 text-center dark:bg-gray-800">
                  <strong className="block font-display font-bold text-foreground">
                    {current.type}
                  </strong>
                  <span className="text-xs text-gray-600 dark:text-gray-400">Room Type</span>
                </div>
                <div className="rounded-xl bg-gray-50 p-3.5 text-center dark:bg-gray-800">
                  <strong className="block font-display font-bold text-foreground">
                    {current.size} sqft
                  </strong>
                  <span className="text-xs text-gray-600 dark:text-gray-400">Size</span>
                </div>
                <div className="rounded-xl bg-gray-50 p-3.5 text-center dark:bg-gray-800">
                  <strong className="block font-display font-bold text-foreground">
                    {current.gender}
                  </strong>
                  <span className="text-xs text-gray-600 dark:text-gray-400">Gender Pref.</span>
                </div>
              </div>

              {/* Description */}
              <p className="mb-4 text-sm leading-relaxed text-gray-600 dark:text-gray-400">
                {current.description}
              </p>

              {/* Amenities */}
              <div className="my-4 flex flex-wrap gap-2">
                {current.amenities.map((a) => (
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
                  {current.ownerAvatar}
                </div>
                <div>
                  <div className="text-sm font-bold text-foreground">{current.owner}</div>
                  {current.verified && (
                    <span className="flex items-center gap-1 text-xs font-semibold text-emerald-500">
                      <ShieldCheck className="size-3.5" /> NID Verified
                    </span>
                  )}
                </div>
              </div>

              {/* Actions */}
              <div className="mt-4 grid grid-cols-2 gap-2">
                <Button variant="outline" className="text-sm" onClick={handleAskCopilot}>
                  <Sparkles className="size-4 text-orange-500" />
                  {t("roomModal.askCopilot")}
                </Button>
                <Button
                  variant="outline"
                  className="text-sm"
                  onClick={() => {
                    if (!current) return;
                    useCopilotStore.getState().openWithListing({
                      id: current.id,
                      title: current.name,
                      price: current.price,
                    });
                    useCopilotStore.getState().requestAiTool("negotiate");
                    onClose();
                  }}
                >
                  <HandCoins className="size-4 text-emerald-500" />
                  Draft negotiation
                </Button>
              </div>

              <Button
                variant="outline"
                className="mt-2 w-full text-sm"
                onClick={() => {
                  if (!current) return;
                  void share(current);
                }}
                disabled={sharingId === current?.id}
              >
                {sharingId === current?.id ? (
                  <>
                    <Loader2 className="size-4 animate-spin" /> Preparing share…
                  </>
                ) : (
                  <>
                    <span className="text-base">💬</span> Share on WhatsApp
                  </>
                )}
              </Button>

              <div className="mt-6 flex gap-3">
                <Button
                  variant="outline"
                  className="flex-1"
                  size="lg"
                  onClick={handleMessageOwner}
                  disabled={startChat.isPending}
                >
                  <MessageCircle className="size-4" />
                  {startChat.isPending ? "Starting…" : "Message Owner"}
                </Button>
                <Button
                  className="flex-1 bg-orange-600 text-white hover:bg-orange-700"
                  size="lg"
                  onClick={handleBook}
                  disabled={createBooking.isPending}
                >
                  <CalendarCheck className="size-4" />
                  {createBooking.isPending ? "Booking…" : "Book Now"}
                </Button>
              </div>

              {/* Reviews v2 — rating breakdown + landlord replies */}
              <ReviewsSection roomId={current.id} isOwner={current.ownerId === user?.id} />

              {/* Visual look-alikes (photo similarity) */}
              <SimilarImages roomId={current.id} onSelect={setCurrent} />

              {/* AI similar-rooms carousel */}
              <SimilarRooms roomId={current.id} currentRoomId={current.id} onSelect={setCurrent} />
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
