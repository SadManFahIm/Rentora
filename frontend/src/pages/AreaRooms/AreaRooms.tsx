import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { MapPin, SearchX, Sparkles } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useRooms, useRoom } from "../../hooks/useRooms";
import { useSeo } from "../../hooks/useSeo";
import { getAreaBySlug } from "../../data/areas";
import RoomCard from "../../components/RoomCard/RoomCard";
import RoomCardSkeleton from "../../components/RoomCardSkeleton";
import RoomModal from "../../components/RoomModal/RoomModal";
import { Button } from "../../components/ui/button";
import type { Room } from "../../types";

/**
 * Area landing page (Phase 13 — SEO reach).
 *
 * Serves `/rooms/:areaSlug` with a search-friendly title/description and the
 * live, real listings for that exact `Room.area` — no fabricated content.
 * `?room=<id>` opens the room modal directly, which is what a WhatsApp-shared
 * link points at. Unknown slugs render a friendly 404-style empty state.
 */
export default function AreaRooms() {
  const { areaSlug = "" } = useParams();
  const [searchParams] = useSearchParams();
  const { t } = useTranslation();
  const area = getAreaBySlug(areaSlug);

  useSeo(
    area ? area.title : "Rooms for rent in Dhaka",
    area
      ? area.description
      : "Find verified rooms for rent across Dhaka — search by area, price and room type on Rentora."
  );

  const { data: rooms = [], isLoading } = useRooms(
    area ? { area: area.area } : { area: "__none__" }
  );
  const [selectedRoom, setSelectedRoom] = useState<Room | null>(null);

  // Deep link support: `?room=<id>` opens the room modal (share destination).
  const roomParam = searchParams.get("room");
  const { data: deepLinkRoom } = useRoom(area ? Number(roomParam) || null : null);

  useEffect(() => {
    if (deepLinkRoom) setSelectedRoom(deepLinkRoom);
  }, [deepLinkRoom]);

  if (!area) {
    return (
      <div className="mx-auto flex max-w-7xl flex-col items-center px-4 py-20 text-center">
        <SearchX className="mb-4 size-12 text-muted-foreground" />
        <h1 className="font-display text-2xl font-bold text-foreground">Area not found</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          We don't have a page for that area yet. Browse all rooms instead.
        </p>
        <Link to="/rooms" className="mt-6">
          <Button variant="brand">Browse all rooms</Button>
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-10 md:px-6 lg:px-8">
      {/* Hero */}
      <div className="relative mb-8 overflow-hidden rounded-2xl bg-gradient-to-br from-indigo-950 via-violet-950 to-slate-950 px-6 py-10 text-white sm:px-10">
        <div className="pointer-events-none absolute -right-8 -top-10 size-40 rounded-full bg-orange-500/30 blur-2xl" />
        <div className="pointer-events-none absolute -bottom-12 left-1/3 size-40 rounded-full bg-sky-400/25 blur-2xl" />
        <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold tracking-wide text-orange-300 uppercase">
          <Sparkles className="size-3.5" /> Rentora · Verified rooms for rent
        </p>
        <h1 className="max-w-2xl font-display text-2xl font-extrabold tracking-tight sm:text-3xl">
          {area.title}
        </h1>
        <p className="mt-3 max-w-2xl text-sm leading-relaxed text-indigo-100/80">
          {area.description}
        </p>
        <div className="mt-5 flex flex-wrap gap-2">
          {area.keywords.slice(0, 3).map((k) => (
            <span
              key={k}
              className="rounded-full border border-white/15 bg-white/5 px-3 py-1 text-xs text-white/70"
            >
              {k}
            </span>
          ))}
        </div>
      </div>

      <div className="mb-5 flex items-center justify-between">
        <h2 className="flex items-center gap-2 font-display text-lg font-bold text-foreground">
          <MapPin className="size-4 text-orange-600" />
          {t("areaRooms.availableIn", { area: area.area })}
        </h2>
        {isLoading ? (
          <span className="text-sm text-muted-foreground">Loading…</span>
        ) : (
          <span className="text-sm text-muted-foreground">{rooms.length} listings</span>
        )}
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <RoomCardSkeleton key={i} />
          ))}
        </div>
      ) : rooms.length === 0 ? (
        <div className="flex flex-col items-center py-16 text-center">
          <SearchX className="mb-4 size-12 text-muted-foreground" />
          <h3 className="font-display text-lg font-bold text-foreground">
            No rooms available in {area.area} right now
          </h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Check back soon, or browse all rooms across Dhaka.
          </p>
          <Link to="/rooms" className="mt-6">
            <Button variant="outline">Browse all rooms</Button>
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {rooms.map((room) => (
            <RoomCard key={room.id} room={room} onClick={setSelectedRoom} />
          ))}
        </div>
      )}

      {selectedRoom && <RoomModal room={selectedRoom} onClose={() => setSelectedRoom(null)} />}
    </div>
  );
}
