import { useState } from "react";
import { LayoutGrid, List, SearchX } from "lucide-react";
import { useRooms } from "../../hooks/useRooms";
import RoomCard from "../../components/RoomCard/RoomCard";
import RoomCardSkeleton from "../../components/RoomCardSkeleton";
import RoomModal from "../../components/RoomModal/RoomModal";
import SearchFilter from "../../components/SearchFilter/SearchFilter";
import AIRecommendations from "../../components/AIRecommendations/AIRecommendations";
import { Button } from "../../components/ui/button";
import type { Room, Filters } from "../../types";
import { cn } from "../../lib/utils";

const DEFAULT_FILTERS: Filters = {
  query: "",
  area: "All",
  type: "All",
  sort: "default",
  amenities: [],
  gender: "Any",
  available: "any",
  minPrice: "",
  maxPrice: "",
};

export default function Rooms() {
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [gridView, setGridView] = useState(true);
  const [selectedRoom, setSelectedRoom] = useState<Room | null>(null);

  // Filtering + sorting happen in the service layer (mock server-side).
  const { data: rooms = [], isLoading } = useRooms(filters);

  return (
    <>
      <SearchFilter filters={filters} setFilters={setFilters} />

      <div className="mx-auto max-w-300 px-4 py-8 sm:px-8">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h2 className="font-display text-xl font-bold text-foreground sm:text-2xl">Available Rooms</h2>
            <p className="text-sm text-muted-foreground">
              {isLoading ? "Loading…" : `${rooms.length} listings found`}
            </p>
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="icon"
              className={cn("rounded-lg", gridView && "border-brand bg-brand/10 text-brand")}
              onClick={() => setGridView(true)}
            >
              <LayoutGrid className="size-4" />
            </Button>
            <Button
              variant="outline"
              size="icon"
              className={cn("rounded-lg", !gridView && "border-brand bg-brand/10 text-brand")}
              onClick={() => setGridView(false)}
            >
              <List className="size-4" />
            </Button>
          </div>
        </div>

        <AIRecommendations />

        {isLoading ? (
          <div className={gridView ? "grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3" : "grid grid-cols-1 gap-4"}>
            {Array.from({ length: 6 }).map((_, i) => (
              <RoomCardSkeleton key={i} />
            ))}
          </div>
        ) : rooms.length === 0 ? (
          <div className="flex flex-col items-center px-5 py-15 text-center text-muted-foreground">
            <SearchX className="mb-4 size-12" />
            <h3 className="mb-2 font-display text-lg font-bold text-foreground">No rooms found</h3>
            <p>Try adjusting your filters</p>
          </div>
        ) : (
          <div className={gridView ? "grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3" : "grid grid-cols-1 gap-4"}>
            {rooms.map((r) => <RoomCard key={r.id} room={r} onClick={setSelectedRoom} />)}
          </div>
        )}
      </div>

      {selectedRoom && <RoomModal room={selectedRoom} onClose={() => setSelectedRoom(null)} />}
    </>
  );
}
