/**
 * MapSearchBar — the floating street/area search bar with autocomplete.
 *
 * Provides a text input with debounced geocoding and an autocomplete
 * dropdown. Supports keyboard navigation (arrow keys, Enter, Escape).
 *
 * Extracted from the monolithic Map.tsx to keep the main component focused
 * on map orchestration.
 */

import { type KeyboardEvent as ReactKeyboardEvent } from "react";
import { Search, X } from "lucide-react";
import type { GeocodeSuggestion } from "../../types";
import { SuggestionIcon } from "./mapHelpers";
import { cn } from "../../lib/utils";

interface MapSearchBarProps {
  searchQuery: string;
  onSearchQueryChange: (query: string) => void;
  searchOpen: boolean;
  onSearchOpenChange: (open: boolean) => void;
  activeSuggestion: number;
  onActiveSuggestionChange: (index: number | ((prev: number) => number)) => void;
  suggestions: GeocodeSuggestion[];
  searching: boolean;
  debouncedSearchQuery: string;
  onSelect: (suggestion: GeocodeSuggestion) => void;
  // Matches useRef<HTMLInputElement>(null) return type in React 18
  inputRef: { readonly current: HTMLInputElement | null };
}

export default function MapSearchBar({
  searchQuery,
  onSearchQueryChange,
  searchOpen,
  onSearchOpenChange,
  activeSuggestion,
  onActiveSuggestionChange,
  suggestions,
  searching,
  debouncedSearchQuery,
  onSelect,
  inputRef,
}: MapSearchBarProps) {
  const onSearchKeyDown = (e: ReactKeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Escape") {
      onSearchOpenChange(false);
      return;
    }
    if (e.key === "Enter") {
      const hit = suggestions[activeSuggestion] ?? suggestions[0];
      if (hit) {
        e.preventDefault();
        onSelect(hit);
      }
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      onActiveSuggestionChange((i) => Math.min(i + 1, Math.max(suggestions.length - 1, 0)));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      onActiveSuggestionChange((i) => Math.max(i - 1, 0));
    }
  };

  return (
    <div className="absolute left-1/2 top-4 z-20 w-[min(22rem,calc(100%-2rem))] -translate-x-1/2">
      <div className="relative">
        <Search className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-gray-400 dark:text-gray-500" />
        <input
          ref={inputRef}
          value={searchQuery}
          onChange={(e) => {
            onSearchQueryChange(e.target.value);
            onSearchOpenChange(true);
            onActiveSuggestionChange(() => 0);
          }}
          onFocus={() => onSearchOpenChange(true)}
          onBlur={() => setTimeout(() => onSearchOpenChange(false), 150)}
          onKeyDown={onSearchKeyDown}
          placeholder="Search streets, areas, stations…"
          aria-label="Search for a street, area or station"
          className="h-11 w-full rounded-xl border border-gray-200 bg-white/95 pl-10 pr-9 text-sm shadow-lg backdrop-blur transition-colors placeholder:text-gray-400 focus:border-violet-400 focus:outline-none focus:ring-2 focus:ring-violet-200 dark:border-gray-700 dark:bg-gray-900/95 dark:placeholder:text-gray-500 dark:focus:border-violet-500 dark:focus:ring-violet-900"
        />
        {searchQuery && (
          <button
            onClick={() => {
              onSearchQueryChange("");
              onSearchOpenChange(false);
              inputRef.current?.focus();
            }}
            aria-label="Clear search"
            className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded-full p-1 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800 dark:hover:text-gray-300"
          >
            <X className="size-4" />
          </button>
        )}
      </div>

      {/* Autocomplete dropdown */}
      {searchOpen && debouncedSearchQuery.trim().length >= 2 && (
        <div className="absolute inset-x-0 top-full z-20 mt-1.5 overflow-hidden rounded-xl border border-gray-200 bg-white/95 shadow-xl backdrop-blur dark:border-gray-700 dark:bg-gray-900/95">
          {searching ? (
            <div className="flex items-center gap-2 px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
              <span className="size-3 animate-spin rounded-full border-2 border-violet-500 border-t-transparent" />
              Searching…
            </div>
          ) : suggestions.length === 0 ? (
            <div className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
              No places found — try "Gulshan", "Mirpur Road" or "Shahbagh".
            </div>
          ) : (
            <ul role="listbox" aria-label="Search suggestions">
              {suggestions.map((s, i) => (
                <li key={s.key}>
                  <button
                    role="option"
                    aria-selected={i === activeSuggestion}
                    onMouseEnter={() => onActiveSuggestionChange(() => i)}
                    onClick={() => onSelect(s)}
                    className={cn(
                      "flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm transition-colors",
                      i === activeSuggestion
                        ? "bg-violet-50 dark:bg-violet-950/40"
                        : "hover:bg-gray-50 dark:hover:bg-gray-800/60"
                    )}
                  >
                    <SuggestionIcon kind={s.kind} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-foreground">{s.label}</span>
                      {s.parent_name && (
                        <span className="block truncate text-[11px] text-gray-400 dark:text-gray-500">
                          {s.parent_name} · {s.kind}
                        </span>
                      )}
                    </span>
                    {!s.parent_name && (
                      <span className="shrink-0 text-[11px] font-medium uppercase tracking-wide text-gray-400 dark:text-gray-500">
                        {s.kind}
                      </span>
                    )}
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
