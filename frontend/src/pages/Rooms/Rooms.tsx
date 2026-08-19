import { useEffect, useRef, useState } from "react";
import { Camera, LayoutGrid, List, SearchX, Sparkles, X } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useRooms, useSmartRooms } from "../../hooks/useRooms";
import { useOfflineCacheStatus } from "../../hooks/useOfflineCacheStatus";
import RoomCard from "../../components/RoomCard/RoomCard";
import RoomCardSkeleton from "../../components/RoomCardSkeleton";
import RoomModal from "../../components/RoomModal/RoomModal";
import SearchFilter from "../../components/SearchFilter/SearchFilter";
import AIRecommendations from "../../components/AIRecommendations/AIRecommendations";
import SavedSearchBar from "../../components/SavedSearchBar/SavedSearchBar";
import CompareDrawer from "../../components/CompareDrawer/CompareDrawer";
import ImageSearchDialog from "../../components/ImageSearchDialog/ImageSearchDialog";
import { Button } from "../../components/ui/button";
import type { Room, Filters } from "../../types";
import type { VisionMatch } from "../../services/visionService";
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
  smart: false,
};

export default function Rooms() {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [filters, setFilters] = useState<Filters>(() => ({
    ...DEFAULT_FILTERS,
    query: searchParams.get("q") ?? "",
  }));
  const [gridView, setGridView] = useState(true);
  const offline = useOfflineCacheStatus();
  const [selectedRoom, setSelectedRoom] = useState<Room | null>(null);
  const [compareIds, setCompareIds] = useState<number[]>([]);
  const [imageSearchOpen, setImageSearchOpen] = useState(false);
  const [imageMatches, setImageMatches] = useState<VisionMatch[] | null>(null);

  const toggleCompare = (room: Room) => {
    setCompareIds((ids) =>
      ids.includes(room.id) ? ids.filter((i) => i !== room.id) : [...ids, room.id].slice(0, 5)
    );
  };
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

  // Smart mode (AI toggle): semantic ranking + natural-language parsing,
  // with the backend's "what was understood" chips shown above the list.
  const smartActive = Boolean(filters.smart);
  const smart = useSmartRooms(filters);
  const regular = useRooms(filters);
  const rooms = smartActive ? (smart.data?.rooms ?? []) : (regular.data ?? []);
  const isLoading = smartActive ? smart.isLoading : regular.isLoading;
  const nlHints = smartActive ? (smart.data?.nlParsed?.hints ?? []) : [];

  const gridClass = gridView
    ? "grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3"
    : "grid grid-cols-1 gap-6";

  return (
    <>
      <SearchFilter filters={filters} setFilters={setFilters} />
      <div className="mx-auto mt-4 flex max-w-7xl items-center justify-between gap-3 px-4 md:px-6 lg:px-8">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          {smartActive && nlHints.length > 0 && (
            <>
              <span className="flex items-center gap-1 text-xs font-semibold text-orange-600 dark:text-orange-400">
                <Sparkles className="size-3.5" /> AI understood:
              </span>
              {nlHints.map((hint) => (
                <span
                  key={hint}
                  className="rounded-full border border-orange-300 bg-orange-50 px-2.5 py-0.5 text-xs font-medium text-orange-700 dark:border-orange-800 dark:bg-orange-950/40 dark:text-orange-300"
                >
                  {hint}
                </span>
              ))}
            </>
          )}
        </div>
        <SavedSearchBar filters={filters} />
      </div>

      <div className="mx-auto max-w-7xl px-4 py-12 md:px-6 md:py-16 lg:px-8">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h2 className="font-display text-xl font-bold text-foreground sm:text-2xl">
              Available Rooms
            </h2>
            <p className="flex flex-wrap items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
              {isLoading ? "Loading…" : `${rooms.length} listings found`}
              {offline.stale && (
                <span className="inline-flex items-center gap-1 rounded-full border border-amber-300 bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700 dark:border-amber-700 dark:bg-amber-950/60 dark:text-amber-300">
                  📡 showing {offline.servedCount} cached of {offline.cachedTotal} (offline)
                </span>
              )}
            </p>
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              className="gap-1.5 rounded-lg"
              onClick={() => setImageSearchOpen(true)}
              aria-label={t("vision.imageSearch")}
            >
              <Camera className="size-4 text-orange-600" />
              <span className="hidden sm:inline">{t("vision.imageSearch")}</span>
            </Button>
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

        {imageMatches !== null ? (
          <>
            <div className="mb-4 flex items-center justify-between gap-3 rounded-xl border border-orange-300 bg-orange-50 px-4 py-2.5 dark:border-orange-900 dark:bg-orange-950/40">
              <p className="flex items-center gap-2 text-sm font-medium text-orange-800 dark:text-orange-300">
                <Sparkles className="size-4" />
                {t("vision.matches", { count: imageMatches.length })}
              </p>
              <button
                type="button"
                onClick={() => setImageMatches(null)}
                className="flex items-center gap-1 rounded-full bg-white/70 px-3 py-1 text-xs font-semibold text-orange-700 transition hover:bg-white dark:bg-gray-900/60 dark:text-orange-300"
              >
                <X className="size-3" />
                {t("vision.clear")}
              </button>
            </div>
            {imageMatches.length === 0 ? (
              <div className="flex flex-col items-center px-5 py-15 text-center text-gray-600 dark:text-gray-400">
                <SearchX className="mb-4 size-12" />
                <h3 className="mb-2 font-display text-lg font-bold text-foreground">
                  {t("vision.noMatches")}
                </h3>
              </div>
            ) : (
              <div className={gridClass}>
                {imageMatches.map((r) => (
                  <RoomCard
                    key={r.id}
                    room={r}
                    onClick={setSelectedRoom}
                    matchInfo={{ score: r.match_score, reasons: r.reasons }}
                  />
                ))}
              </div>
            )}
          </>
        ) : isLoading ? (
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
              <RoomCard
                key={r.id}
                room={r}
                onClick={setSelectedRoom}
                compareSelected={compareIds.includes(r.id)}
                onToggleCompare={toggleCompare}
              />
            ))}
          </div>
        )}
      </div>

      {selectedRoom && <RoomModal room={selectedRoom} onClose={() => setSelectedRoom(null)} />}

      {compareIds.length > 0 && (
        <CompareDrawer
          roomIds={compareIds}
          onRemove={(id) => setCompareIds((ids) => ids.filter((i) => i !== id))}
          onClear={() => setCompareIds([])}
        />
      )}

      <ImageSearchDialog
        open={imageSearchOpen}
        onClose={() => setImageSearchOpen(false)}
        onResult={setImageMatches}
      />
    </>
  );
}
