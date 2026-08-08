// Map Page — interactive Leaflet map with a synced room list (Phase 7).
import { useState } from "react";
import { Star, MapPinOff, Loader2 } from "lucide-react";

import { useRoomsInBounds } from "../../hooks/useRooms";
import RoomModal from "../../components/RoomModal/RoomModal";
import type { Room } from "../../types";
import { cn } from "../../lib/utils";
import RoomMap from "./RoomMap";

export default function Map() {
  // `bbox` null on first render → load the whole available set (and fit to it);
  // panning/zooming the map then drives viewport-scoped refetches.
  const [bbox, setBbox] = useState<string | null>(null);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [selected, setSelected] = useState<Room | null>(null);

  const { data: rooms = [], isLoading, isFetching } = useRoomsInBounds(bbox);

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 md:px-6 md:py-10 lg:px-8">
      <div className="mb-5 flex items-center justify-between">
        <div>
          <h2 className="font-display text-xl font-bold text-foreground sm:text-2xl">🗺️ Map View</h2>
          <p className="flex items-center gap-1.5 text-sm text-gray-600 dark:text-gray-400">
            {isLoading ? "Loading rooms…" : `${rooms.length} room${rooms.length === 1 ? "" : "s"} in view`}
            {isFetching && !isLoading && <Loader2 className="size-3.5 animate-spin" />}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Map */}
        <div className="z-0 h-[50vh] overflow-hidden rounded-2xl border border-gray-200 dark:border-gray-800 lg:col-span-2 lg:h-[72vh]">
          <RoomMap
            rooms={rooms}
            activeId={activeId}
            onHover={setActiveId}
            onSelect={setSelected}
            onBoundsChange={setBbox}
          />
        </div>

        {/* Synced list */}
        <div className="flex max-h-[72vh] flex-col gap-3 overflow-y-auto pr-1">
          {rooms.length === 0 && !isLoading ? (
            <div className="flex flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-gray-300 py-12 text-center text-gray-500 dark:border-gray-700">
              <MapPinOff className="size-8" />
              <p className="text-sm font-medium">No rooms in this area</p>
              <p className="text-xs">Try panning or zooming out.</p>
            </div>
          ) : (
            rooms.map((room) => (
              <button
                type="button"
                key={room.id}
                onMouseEnter={() => setActiveId(room.id)}
                onMouseLeave={() => setActiveId(null)}
                onClick={() => setSelected(room)}
                className={cn(
                  "flex gap-3 rounded-xl border bg-card p-2.5 text-left transition-colors",
                  room.id === activeId
                    ? "border-orange-600 ring-1 ring-orange-600"
                    : "border-gray-200 hover:border-orange-300 dark:border-gray-800",
                )}
              >
                <img
                  src={room.img}
                  alt={room.name}
                  className="size-20 shrink-0 rounded-lg object-cover"
                  loading="lazy"
                />
                <div className="min-w-0 flex-1">
                  <div className="flex items-start justify-between gap-2">
                    <p className="truncate text-sm font-bold text-foreground">{room.name}</p>
                    <span className="flex shrink-0 items-center gap-0.5 text-xs font-semibold text-gray-600 dark:text-gray-400">
                      <Star className="size-3 fill-amber-400 text-amber-400" />
                      {room.rating.toFixed(1)}
                    </span>
                  </div>
                  <p className="text-xs text-gray-500">
                    {room.area} · {room.type}
                  </p>
                  {room.proximity?.nearestUniversity && (
                    <p className="mt-0.5 truncate text-xs text-gray-500">
                      🏫 {room.proximity.nearestUniversity.distanceKm} km · {room.proximity.nearestUniversity.name}
                    </p>
                  )}
                  <p className="mt-1 text-sm font-extrabold text-orange-600">
                    ৳{room.price.toLocaleString()}
                    <span className="text-xs font-normal text-gray-500">/mo</span>
                  </p>
                </div>
              </button>
            ))
          )}
        </div>
      </div>

      {selected && <RoomModal room={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
