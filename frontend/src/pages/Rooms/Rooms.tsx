import { useEffect, useRef, useState } from "react";
import { LayoutGrid, List, SearchX } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { useRooms } from "../../hooks/useRooms";
import RoomCard from "../../components/RoomCard/RoomCard";
import RoomCardSkeleton from "../../components/RoomCardSkeleton";
import RoomModal from "../../components/RoomModal/RoomModal";
import SearchFilter from "../../components/SearchFilter/SearchFilter";
import AIRecommendations from "../../components/AIRecommendations/AIRecommendations";
import SavedSearchBar from "../../components/SavedSearchBar/SavedSearchBar";
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
  verified: false,
};

export default function Rooms() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [filters, setFilters] = useState<Filters>(() => ({
    ...DEFAULT_FILTERS,
    query: searchParams.get("q") ?? "",
  }));
  const [gridView, setGridView] = useState(true);
  const [selectedRoom, setSelectedRoom] = useState<Room | null>(null);
  // Set when a URL-initiated change is applied to state, so the reverse sync
  // skips that pass instead of clobbering the URL with stale state.
  const fromUrlRef = useRef(false);

  // Sync URL param -> state so back/forward and direct ?q= links update the list.
  useEffect(() => {
    const q = searchParams.get("q") ?? "";
    setFilters((f) => (f.query === q ? f : { ...f, query: q }));
    // Set synchronously (not inside the updater, which runs after effects):
    // mark this pass so the reverse sync skips and doesn't clobber a URL
    // change (e.g. clicking a plain "/rooms" link) with stale state.
    // Unconditional set is deliberate: when state already matches, the skip
    // is a no-op, and when it doesn't, the skip prevents the clobber. Keep
    // this OUTSIDE the setFilters updater — inside it runs too late.
    fromUrlRef.current = true;
  }, [searchParams]);

  // Sync state -> URL param so searches are shareable/bookmarkable.
  useEffect(() => {
    if (fromUrlRef.current) {
      fromUrlRef.current = false;
      return;
    }
    const q = searchParams.get("q") ?? "";
    if (filters.query === q) return;
    const params = new URLSearchParams(searchParams);
    if (filters.query) {
      params.set("q", filters.query);
    } else {
      params.delete("q");
    }
    setSearchParams(params, { replace: true });
  }, [filters.query, searchParams, setSearchParams]);

  // Filtering + sorting happen in the service layer (mock server-side).
  const { data: rooms = [], isLoading } = useRooms(filters);

  const gridClass = gridView
    ? "grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3"
    : "grid grid-cols-1 gap-6";

  return (
    <>
      <SearchFilter filters={filters} setFilters={setFilters} />
      <div className="mx-auto mt-4 flex max-w-7xl justify-end px-4 md:px-6 lg:px-8">
        <SavedSearchBar filters={filters} />
      </div>

      <div className="mx-auto max-w-7xl px-4 py-12 md:px-6 md:py-16 lg:px-8">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h2 className="font-display text-xl font-bold text-foreground sm:text-2xl">
              Available Rooms
            </h2>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              {isLoading ? "Loading…" : `${rooms.length} listings found`}
            </p>
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="icon"
              aria-label="Grid view"
              className={cn(
                "rounded-lg",
                gridView && "border-orange-600 bg-orange-50 text-orange-600 dark:bg-orange-950/40"
              )}
              onClick={() => setGridView(true)}
            >
              <LayoutGrid className="size-4" />
            </Button>
            <Button
              variant="outline"
              size="icon"
              aria-label="List view"
              className={cn(
                "rounded-lg",
                !gridView && "border-orange-600 bg-orange-50 text-orange-600 dark:bg-orange-950/40"
              )}
              onClick={() => setGridView(false)}
            >
              <List className="size-4" />
            </Button>
          </div>
        </div>

        <AIRecommendations />

        {isLoading ? (
          <div className={gridClass}>
            {Array.from({ length: 6 }).map((_, i) => (
              <RoomCardSkeleton key={i} />
            ))}
          </div>
        ) : rooms.length === 0 ? (
          <div className="flex flex-col items-center px-5 py-15 text-center text-gray-600 dark:text-gray-400">
            <SearchX className="mb-4 size-12" />
            <h3 className="mb-2 font-display text-lg font-bold text-foreground">No rooms found</h3>
            <p>Try adjusting your filters</p>
          </div>
        ) : (
          <div className={gridClass}>
            {rooms.map((r) => (
              <RoomCard key={r.id} room={r} onClick={setSelectedRoom} />
            ))}
          </div>
        )}
      </div>

      {selectedRoom && <RoomModal room={selectedRoom} onClose={() => setSelectedRoom(null)} />}
    </>
  );
}
