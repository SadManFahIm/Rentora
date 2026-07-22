import { useState } from "react";
import { Search, SlidersHorizontal, X } from "lucide-react";
import { AREAS, ROOM_TYPES, AMENITIES_LIST } from "../../data/mockData";
import type { Filters, SortOption, GenderPref } from "../../types";
import { Input } from "../ui/input";
import { Button } from "../ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";
import { cn } from "../../lib/utils";

interface SearchFilterProps {
  filters: Filters;
  setFilters: React.Dispatch<React.SetStateAction<Filters>>;
}

const SORT_OPTIONS: { value: SortOption; label: string }[] = [
  { value: "default", label: "Sort: Default" },
  { value: "price-asc", label: "Price: Low→High" },
  { value: "price-desc", label: "Price: High→Low" },
  { value: "rating", label: "Top Rated" },
];

export default function SearchFilter({ filters, setFilters }: SearchFilterProps) {
  const [showPanel, setShowPanel] = useState(false);

  const update = <K extends keyof Filters>(key: K, value: Filters[K]) =>
    setFilters((f) => ({ ...f, [key]: value }));

  const toggleAmenity = (a: string) =>
    setFilters((f) => ({
      ...f,
      amenities: f.amenities.includes(a)
        ? f.amenities.filter((x) => x !== a)
        : [...f.amenities, a],
    }));

  const reset = () => {
    setFilters({
      query: "",
      area: "All",
      type: "All",
      sort: "default",
      amenities: [],
      gender: "Any",
      available: "any",
      minPrice: "",
      maxPrice: "",
    });
    setShowPanel(false);
  };

  return (
    <>
      {/* Main Search Bar */}
      <div className="sticky top-16 z-90 border-b border-border bg-card px-4 py-5 sm:px-8">
        <div className="mx-auto flex max-w-300 flex-wrap items-center gap-3">
          <div className="relative min-w-60 flex-1">
            <Search className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              className="h-11 rounded-xl pl-10"
              placeholder="Search by name or area..."
              value={filters.query}
              onChange={(e) => update("query", e.target.value)}
            />
          </div>

          <div className="hidden flex-wrap gap-2 lg:flex">
            {AREAS.map((a) => (
              <button
                key={a}
                className={cn(
                  "rounded-lg border px-4 py-2.5 text-sm font-medium transition-colors",
                  filters.area === a
                    ? "border-brand bg-brand/10 text-brand"
                    : "border-border bg-background text-muted-foreground hover:border-brand hover:text-brand"
                )}
                onClick={() => update("area", a)}
              >
                {a === "All" ? "All Areas" : a}
              </button>
            ))}
            {ROOM_TYPES.map((t) => (
              <button
                key={t}
                className={cn(
                  "rounded-lg border px-4 py-2.5 text-sm font-medium transition-colors",
                  filters.type === t
                    ? "border-brand bg-brand/10 text-brand"
                    : "border-border bg-background text-muted-foreground hover:border-brand hover:text-brand"
                )}
                onClick={() => update("type", t)}
              >
                {t === "All" ? "All Types" : t}
              </button>
            ))}
          </div>

          <Button variant="outline" className="h-11 rounded-xl" onClick={() => setShowPanel(true)}>
            <SlidersHorizontal className="size-4" /> Advanced
          </Button>

          <Select value={filters.sort} onValueChange={(v) => update("sort", v as SortOption)}>
            <SelectTrigger className="h-11 rounded-xl">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {SORT_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Filter Panel */}
      {showPanel && (
        <div
          className="fixed inset-0 z-199 bg-black/40"
          onClick={() => setShowPanel(false)}
        />
      )}
      <div
        className={cn(
          "fixed right-0 top-0 z-200 h-screen w-full max-w-90 translate-x-full overflow-y-auto border-l border-border bg-card p-6 transition-transform duration-300",
          showPanel && "translate-x-0"
        )}
      >
        <div className="mb-6 flex items-center justify-between">
          <h3 className="font-display text-lg font-bold text-foreground">Advanced Filters</h3>
          <Button variant="outline" size="icon" className="rounded-full" onClick={() => setShowPanel(false)}>
            <X className="size-4" />
          </Button>
        </div>

        {/* Mobile-only area/type chips (hidden lg:flex bar above is desktop-only) */}
        <div className="mb-6 lg:hidden">
          <label className="mb-2.5 block text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Area
          </label>
          <div className="flex flex-wrap gap-2">
            {AREAS.map((a) => (
              <button
                key={a}
                className={cn(
                  "rounded-lg border px-3.5 py-2 text-sm transition-colors",
                  filters.area === a
                    ? "border-brand bg-brand/10 text-brand"
                    : "border-border bg-background text-muted-foreground"
                )}
                onClick={() => update("area", a)}
              >
                {a === "All" ? "All Areas" : a}
              </button>
            ))}
          </div>
          <label className="mb-2.5 mt-4 block text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Room Type
          </label>
          <div className="flex flex-wrap gap-2">
            {ROOM_TYPES.map((t) => (
              <button
                key={t}
                className={cn(
                  "rounded-lg border px-3.5 py-2 text-sm transition-colors",
                  filters.type === t
                    ? "border-brand bg-brand/10 text-brand"
                    : "border-border bg-background text-muted-foreground"
                )}
                onClick={() => update("type", t)}
              >
                {t === "All" ? "All Types" : t}
              </button>
            ))}
          </div>
        </div>

        <div className="mb-6">
          <label className="mb-2.5 block text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Budget Range (৳/month)
          </label>
          <div className="flex gap-2.5">
            <Input
              type="number"
              placeholder="Min"
              value={filters.minPrice}
              onChange={(e) => update("minPrice", e.target.value)}
            />
            <Input
              type="number"
              placeholder="Max"
              value={filters.maxPrice}
              onChange={(e) => update("maxPrice", e.target.value)}
            />
          </div>
        </div>

        <div className="mb-6">
          <label className="mb-2.5 block text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Amenities
          </label>
          <div className="flex flex-wrap gap-2">
            {AMENITIES_LIST.map((a) => (
              <button
                key={a}
                className={cn(
                  "rounded-md border px-3.5 py-1.5 text-sm transition-colors",
                  filters.amenities.includes(a)
                    ? "border-brand bg-brand/10 text-brand"
                    : "border-border bg-background text-muted-foreground"
                )}
                onClick={() => toggleAmenity(a)}
              >
                {a}
              </button>
            ))}
          </div>
        </div>

        <div className="mb-6">
          <label className="mb-2.5 block text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Gender Preference
          </label>
          <div className="flex flex-wrap gap-2">
            {(["Any", "Male", "Female"] as GenderPref[]).map((g) => (
              <button
                key={g}
                className={cn(
                  "rounded-md border px-3.5 py-1.5 text-sm transition-colors",
                  filters.gender === g
                    ? "border-brand bg-brand/10 text-brand"
                    : "border-border bg-background text-muted-foreground"
                )}
                onClick={() => update("gender", g)}
              >
                {g}
              </button>
            ))}
          </div>
        </div>

        <div className="mb-6">
          <label className="mb-2.5 block text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Availability
          </label>
          <div className="flex flex-wrap gap-2">
            <button
              className={cn(
                "rounded-md border px-3.5 py-1.5 text-sm transition-colors",
                filters.available === "any"
                  ? "border-brand bg-brand/10 text-brand"
                  : "border-border bg-background text-muted-foreground"
              )}
              onClick={() => update("available", "any")}
            >
              All
            </button>
            <button
              className={cn(
                "rounded-md border px-3.5 py-1.5 text-sm transition-colors",
                filters.available === "yes"
                  ? "border-brand bg-brand/10 text-brand"
                  : "border-border bg-background text-muted-foreground"
              )}
              onClick={() => update("available", "yes")}
            >
              Available Only
            </button>
          </div>
        </div>

        <Button variant="brand" className="mt-2 w-full" size="lg" onClick={() => setShowPanel(false)}>
          Apply Filters
        </Button>
        <Button variant="outline" className="mt-2 w-full" onClick={reset}>
          Reset All
        </Button>
      </div>
    </>
  );
}
