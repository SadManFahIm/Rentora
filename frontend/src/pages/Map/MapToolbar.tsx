/**
 * MapToolbar — the floating toolbar with layer toggle buttons, radius
 * search slider, area count chips, and university quick-pick chips.
 *
 * Extracted from the monolithic Map.tsx to keep the main component focused
 * on map orchestration. The toolbar is a pure presentational shell — all
 * state and callbacks are passed in as props.
 */

import {
  Bus,
  Church,
  Crosshair,
  Footprints,
  Hospital,
  Landmark as LandmarkIcon,
  List as ListIcon,
  MapPin,
  ShoppingBasket,
  Sparkles,
  Thermometer,
  TrainFront,
  TreePine,
  Users as UsersIcon,
} from "lucide-react";
import { Button } from "../../components/ui/button";
import { cn } from "../../lib/utils";

export type MapLayerId =
  "universities" | "metro" | "hospital" | "market" | "park" | "mosque" | "bus_terminal";

interface MapToolbarProps {
  // Layer toggles
  showLandmarks: Record<MapLayerId, boolean>;
  onToggleLandmark: (id: MapLayerId) => void;
  showAreas: boolean;
  onToggleAreas: () => void;
  heatmap: boolean;
  onToggleHeatmap: () => void;
  clustering: boolean;
  onToggleClustering: () => void;
  showTravel: boolean;
  onToggleTravel: () => void;
  listOpen: boolean;
  onToggleList: () => void;
  intelMode: boolean;
  onToggleIntel: () => void;

  // Radius search
  radiusCenter: { lat: number; lng: number; label: string } | null;
  radiusKm: number;
  onRadiusKmChange: (km: number) => void;
  onClearRadius: () => void;
  showTravelBands: boolean;

  // Area chips
  areaChips: { area: string; count: number; lat: number | null; lng: number | null }[];
  onAreaChipClick: (lat: number, lng: number, label: string) => void;

  // University quick-pick
  universityChips: { key: string; name: string; lat: number; lng: number }[];
  onUniversityClick: (lat: number, lng: number, name: string) => void;
}

export default function MapToolbar({
  showLandmarks,
  onToggleLandmark,
  showAreas,
  onToggleAreas,
  heatmap,
  onToggleHeatmap,
  clustering,
  onToggleClustering,
  showTravel,
  onToggleTravel,
  listOpen,
  onToggleList,
  intelMode,
  onToggleIntel,
  radiusCenter,
  radiusKm,
  onRadiusKmChange,
  onClearRadius,
  showTravelBands,
  areaChips,
  onAreaChipClick,
  universityChips,
  onUniversityClick,
}: MapToolbarProps) {
  return (
    <div className="absolute left-4 top-4 z-10 flex max-w-[calc(100%-2rem)] flex-col gap-3">
      {/* Layer toggles */}
      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-gray-200 bg-white/95 p-2 shadow-lg backdrop-blur dark:border-gray-800 dark:bg-gray-900/95">
        <Button
          variant="ghost"
          size="sm"
          aria-pressed={showLandmarks.universities}
          className={cn(
            "gap-1.5 rounded-lg",
            showLandmarks.universities &&
              "bg-violet-50 text-violet-700 dark:bg-violet-950/40 dark:text-violet-300"
          )}
          onClick={() => onToggleLandmark("universities")}
        >
          <LandmarkIcon className="size-4" /> Universities
        </Button>
        <Button
          variant="ghost"
          size="sm"
          aria-pressed={showLandmarks.metro}
          className={cn(
            "gap-1.5 rounded-lg",
            showLandmarks.metro && "bg-teal-50 text-teal-700 dark:bg-teal-950/40 dark:text-teal-300"
          )}
          onClick={() => onToggleLandmark("metro")}
        >
          <TrainFront className="size-4" /> Metro
        </Button>

        {/* Everyday categories */}
        {(
          [
            ["hospital", Hospital, "Hospitals"],
            ["market", ShoppingBasket, "Markets"],
            ["park", TreePine, "Parks"],
            ["mosque", Church, "Mosques"],
            ["bus_terminal", Bus, "Bus stops"],
          ] as const
        ).map(([kind, Icon, label]) => (
          <Button
            key={kind}
            variant="ghost"
            size="sm"
            aria-pressed={showLandmarks[kind]}
            title="Zoom in to see individual places"
            className={cn(
              "gap-1.5 rounded-lg",
              showLandmarks[kind] &&
                "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300"
            )}
            onClick={() => onToggleLandmark(kind)}
          >
            <Icon className="size-4" /> {label}
          </Button>
        ))}

        <Button
          variant="ghost"
          size="sm"
          aria-pressed={showAreas}
          className={cn(
            "gap-1.5 rounded-lg",
            showAreas && "bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300"
          )}
          onClick={onToggleAreas}
          title="Area boundary bubbles + labels"
        >
          <MapPin className="size-4" /> Areas
        </Button>
        <Button
          variant="ghost"
          size="sm"
          aria-pressed={heatmap}
          className={cn(
            "gap-1.5 rounded-lg",
            heatmap && "bg-orange-50 text-orange-700 dark:bg-orange-950/40 dark:text-orange-300"
          )}
          onClick={onToggleHeatmap}
        >
          <Thermometer className="size-4" /> Price heatmap
        </Button>
        <Button
          variant="ghost"
          size="sm"
          aria-pressed={clustering}
          className={cn(
            "gap-1.5 rounded-lg",
            clustering && "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200"
          )}
          onClick={onToggleClustering}
        >
          <UsersIcon className="size-4" /> {clustering ? "Clustered" : "Pins"}
        </Button>
        <Button
          variant="ghost"
          size="sm"
          aria-pressed={showTravel}
          className={cn(
            "gap-1.5 rounded-lg",
            showTravel && "bg-teal-50 text-teal-700 dark:bg-teal-950/40 dark:text-teal-300"
          )}
          disabled={!radiusCenter}
          onClick={onToggleTravel}
        >
          <Footprints className="size-4" /> Travel
        </Button>
        <Button
          variant="ghost"
          size="sm"
          aria-pressed={listOpen}
          className={cn(
            "gap-1.5 rounded-lg",
            listOpen && "bg-blue-50 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300"
          )}
          onClick={onToggleList}
        >
          <ListIcon className="size-4" /> List
        </Button>
        <Button
          variant="ghost"
          size="sm"
          aria-pressed={!!intelMode}
          className={cn(
            "gap-1.5 rounded-lg",
            intelMode && "bg-violet-50 text-violet-700 dark:bg-violet-950/40 dark:text-violet-300"
          )}
          onClick={onToggleIntel}
        >
          <Sparkles className="size-4" /> AI Map
        </Button>
      </div>

      {/* Radius search */}
      <div className="rounded-xl border border-gray-200 bg-white/95 p-3 shadow-lg backdrop-blur dark:border-gray-800 dark:bg-gray-900/95">
        <div className="mb-1.5 flex items-center gap-2 text-sm font-semibold text-foreground">
          <Crosshair className="size-4 text-blue-600" />
          {radiusCenter ? (
            <span>
              Near {radiusCenter.label} · <span className="text-blue-600">{radiusKm} km</span>
            </span>
          ) : (
            <span>Click the map to search near a point</span>
          )}
        </div>
        {showTravelBands && radiusCenter && (
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-gray-600 dark:text-gray-400">
            <span className="font-semibold">Walking:</span>
            <span className="flex items-center gap-1">
              <span className="inline-block size-2 rounded-full bg-green-500" /> 10 min
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block size-2 rounded-full bg-amber-500" /> 20 min
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block size-2 rounded-full bg-red-500" /> 30 min
            </span>
          </div>
        )}
        <div className="flex items-center gap-2">
          <input
            type="range"
            min={0.5}
            max={5}
            step={0.5}
            value={radiusKm}
            onChange={(e) => onRadiusKmChange(Number(e.target.value))}
            className="h-2 w-full cursor-pointer accent-blue-600"
            aria-label="Search radius in km"
          />
          <Button
            variant="outline"
            size="sm"
            className="shrink-0 rounded-lg text-xs"
            onClick={onClearRadius}
          >
            Clear
          </Button>
        </div>
      </div>

      {/* Area count chips */}
      {!radiusCenter && areaChips.length > 0 && (
        <div className="flex max-w-sm flex-wrap gap-1.5">
          {areaChips.map((chip) => (
            <button
              key={chip.area}
              onClick={() => {
                if (chip.lat == null || chip.lng == null) return;
                onAreaChipClick(chip.lat, chip.lng, chip.area);
              }}
              className="group flex items-center gap-1.5 rounded-full border border-gray-200 bg-white/95 py-1 pl-2.5 pr-1 text-xs font-medium text-gray-700 shadow-sm backdrop-blur transition-colors hover:border-blue-300 hover:bg-blue-50 hover:text-blue-700 dark:border-gray-700 dark:bg-gray-900/95 dark:text-gray-300 dark:hover:border-blue-600 dark:hover:bg-blue-950/40 dark:hover:text-blue-300"
            >
              <MapPin className="size-3 text-blue-600 dark:text-blue-400" />
              {chip.area}
              <span className="flex size-5 items-center justify-center rounded-full bg-gray-100 text-[10px] font-bold text-gray-600 transition-colors group-hover:bg-blue-100 group-hover:text-blue-700 dark:bg-gray-800 dark:text-gray-300 dark:group-hover:bg-blue-900 dark:group-hover:text-blue-200">
                {chip.count}
              </span>
            </button>
          ))}
        </div>
      )}

      {/* University quick-pick chips */}
      {!radiusCenter && (
        <div className="flex max-w-sm flex-wrap gap-1.5">
          {universityChips.map((l) => (
            <button
              key={l.key}
              onClick={() => onUniversityClick(l.lat, l.lng, l.name)}
              className="rounded-full border border-gray-200 bg-white/95 px-3 py-1 text-xs font-medium text-gray-700 shadow-sm backdrop-blur transition-colors hover:border-violet-300 hover:bg-violet-50 hover:text-violet-700 dark:border-gray-700 dark:bg-gray-900/95 dark:text-gray-300 dark:hover:border-violet-600 dark:hover:bg-violet-950/40 dark:hover:text-violet-300"
            >
              🎓 {l.name}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
