import { useState } from "react";
import { BellRing, BookmarkPlus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { useSavedSearches } from "../../hooks/useSavedSearches";
import { isAuthenticated } from "../../services/api";
import type { Filters } from "../../types";
import { Button } from "../ui/button";

interface SavedSearchBarProps {
  filters: Filters;
}

/** Save the current search + manage saved searches (Search v2). */
export default function SavedSearchBar({ filters }: SavedSearchBarProps) {
  const { savedSearches, createSearch, deleteSearch } = useSavedSearches();
  const [open, setOpen] = useState(false);

  const hasFilters =
    filters.query.trim() !== "" || filters.area !== "All" || filters.type !== "All";

  const saveCurrent = () => {
    if (!isAuthenticated()) {
      toast.info("Please sign in to save searches.");
      return;
    }
    const filtersPayload = {
      q: filters.query.trim() || undefined,
      area: filters.area !== "All" ? filters.area : undefined,
      room_type: filters.type !== "All" ? filters.type.toLowerCase() : undefined,
      price_min: filters.minPrice ? Number(filters.minPrice) : undefined,
      price_max: filters.maxPrice ? Number(filters.maxPrice) : undefined,
      verified: filters.verified || undefined,
    };
    createSearch.mutate(
      { name: filters.query.trim() || `${filters.area} rooms`, filters: filtersPayload },
      {
        onSuccess: () => toast.success("Search saved — we'll alert you about new rooms."),
        onError: () => toast.error("Could not save search."),
      }
    );
  };

  return (
    <div className="relative">
      <Button variant="outline" size="sm" className="rounded-lg" onClick={() => setOpen((o) => !o)}>
        <BellRing className="size-4" />
        Saved searches
        {savedSearches.length > 0 && (
          <span className="rounded-full bg-orange-600 px-1.5 text-[10px] font-bold text-white">
            {savedSearches.length}
          </span>
        )}
      </Button>

      {open && (
        <div className="absolute right-0 z-30 mt-2 w-72 rounded-xl border border-gray-200 bg-card p-3 shadow-lg dark:border-gray-700">
          <Button
            size="sm"
            className="mb-2 w-full rounded-lg bg-orange-600 text-white hover:bg-orange-700"
            disabled={!hasFilters || createSearch.isPending}
            onClick={saveCurrent}
          >
            <BookmarkPlus className="size-4" />
            {createSearch.isPending ? "Saving…" : "Save this search"}
          </Button>
          {savedSearches.length === 0 ? (
            <p className="px-1 py-2 text-xs text-gray-600 dark:text-gray-400">
              No saved searches yet — set filters and save to get alerts.
            </p>
          ) : (
            <ul className="max-h-56 space-y-1 overflow-y-auto">
              {savedSearches.map((s) => (
                <li
                  key={s.id}
                  className="flex items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-sm hover:bg-gray-50 dark:hover:bg-gray-800"
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium text-foreground">{s.name}</span>
                    <span className="text-[11px] text-gray-600 dark:text-gray-400">
                      {s.filters.area || "All areas"}
                      {s.lastCheckedAt ? " · alerted" : " · new"}
                    </span>
                  </span>
                  <button
                    aria-label={`Delete ${s.name}`}
                    className="text-gray-500 hover:text-red-500"
                    onClick={() => deleteSearch.mutate(s.id)}
                  >
                    <Trash2 className="size-4" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
