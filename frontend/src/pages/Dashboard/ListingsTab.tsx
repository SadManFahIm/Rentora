/**
 * ListingsTab — landlord's own listings with their paid tier and a promote action.
 *
 * Extracted from the monolithic Dashboard.tsx to keep the main component focused
 * on tab routing and overview stats.
 */

import { Megaphone } from "lucide-react";
import { useApp } from "../../context/AppContext";
import { useRooms } from "../../hooks/useRooms";
import { Button } from "../../components/ui/button";
import TierBadge from "../../components/TierBadge/TierBadge";
import PriceRecommendationCard from "../../components/PriceRecommendationCard/PriceRecommendationCard";
import VisionCard from "../../components/VisionCard/VisionCard";
import type { Room } from "../../types";

interface ListingsTabProps {
  onPromote: (room: Room) => void;
}

export default function ListingsTab({ onPromote }: ListingsTabProps) {
  const { user } = useApp();
  // Server-side owner filter: the landlord dashboard only needs this owner's
  // listings, and a client-side filter over the first page of *all* rooms
  // would silently drop listings beyond page 1.
  const { data: rooms = [], isLoading } = useRooms(
    user?.id != null ? { owner: user.id } : undefined
  );

  const myRooms = rooms;

  if (isLoading) {
    return (
      <div className="py-15 text-center text-gray-600 dark:text-gray-400">
        Loading your listings…
      </div>
    );
  }

  return (
    <div>
      <div className="mb-5 flex items-center gap-2">
        <Megaphone className="size-5 text-orange-600" />
        <div>
          <h2 className="font-display text-lg font-bold text-foreground">My Listings</h2>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Manage your rooms and promote them to reach more tenants.
          </p>
        </div>
      </div>

      {myRooms.length === 0 ? (
        <div className="flex flex-col items-center px-5 py-15 text-center text-gray-600 dark:text-gray-400">
          <Megaphone className="mb-4 size-12" />
          <h3 className="mb-2 font-display text-lg font-bold text-foreground">No listings yet</h3>
          <p>Create a room listing to start renting it out.</p>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {myRooms.map((room) => (
            <div
              key={room.id}
              className="flex flex-col gap-3 rounded-2xl border border-gray-200 bg-card p-4 dark:border-gray-800"
            >
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-center gap-3">
                  <img
                    src={room.img}
                    alt={room.name}
                    className="h-16 w-24 shrink-0 rounded-lg object-cover"
                  />
                  <div>
                    <div className="flex items-center gap-2 font-display text-sm font-bold text-foreground">
                      {room.name}
                      <TierBadge tier={room.tier} showFree />
                    </div>
                    <div className="mt-0.5 text-xs text-gray-600 dark:text-gray-400">
                      {room.area} • ৳{room.price.toLocaleString()}/mo •{" "}
                      {room.available ? "Available" : "Unavailable"}
                    </div>
                    {room.tierExpiresAt && room.tier !== "free" && (
                      <div className="mt-1 text-xs text-amber-600 dark:text-amber-400">
                        {room.tier === "premium" ? "Premium" : "Featured"} until{" "}
                        {new Date(room.tierExpiresAt).toLocaleDateString()}
                      </div>
                    )}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <div className="w-72">
                    <PriceRecommendationCard roomId={room.id} />
                  </div>
                  <Button
                    size="sm"
                    className="shrink-0 bg-orange-600 text-white hover:bg-orange-700"
                    onClick={() => onPromote(room)}
                  >
                    <Megaphone className="mr-1.5 size-3.5" />
                    {room.tier === "free" ? "Promote" : "Upgrade"}
                  </Button>
                </div>
              </div>
              <VisionCard room={room} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
