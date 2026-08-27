/**
 * MapLegend — the floating legend in the bottom-right corner of the map.
 *
 * Shows tier colors (Free/Featured/Premium), area boundary indicators, and
 * landmark categories that are currently toggled on. Switches to a heatmap
 * gradient scale when the price heatmap is active.
 *
 * Extracted from the monolithic Map.tsx to keep the main component focused
 * on map orchestration.
 */

import {
  Bus,
  Church,
  GraduationCap,
  Hospital,
  ShoppingBasket,
  TrainFront,
  TreePine,
} from "lucide-react";
import { LANDMARK_KIND_META } from "../../lib/mapInteractions";
import type { MapLayerId } from "./MapToolbar";

interface MapLegendProps {
  heatmap: boolean;
  showAreas: boolean;
  showLandmarks: Record<MapLayerId, boolean>;
  darkMode: boolean;
  mapZoom: number;
}

export default function MapLegend({
  heatmap,
  showAreas,
  showLandmarks,
  darkMode,
  mapZoom,
}: MapLegendProps) {
  return (
    <div className="absolute bottom-4 right-4 z-10 block rounded-lg border border-gray-200 bg-white/95 px-3 py-2 text-xs shadow backdrop-blur dark:border-gray-800 dark:bg-gray-900/95">
      {heatmap ? (
        <>
          <div className="mb-1 font-semibold text-foreground">Rent heatmap</div>
          <div
            className="h-2 w-36 rounded-full"
            style={{
              background: "linear-gradient(90deg, #22c55e 0%, #f59e0b 50%, #ef4444 100%)",
            }}
          />
          <div className="mt-0.5 flex justify-between text-[10px] text-gray-500 dark:text-gray-400">
            <span>৳5k</span>
            <span>৳15k</span>
            <span>৳30k+</span>
          </div>
        </>
      ) : (
        <>
          <div className="mb-1 font-semibold text-foreground">Legend</div>
          <div className="flex items-center gap-1.5 text-gray-600 dark:text-gray-400">
            <span className="inline-block size-2.5 rounded-full bg-[#ea580c]" /> Free
          </div>
          <div className="flex items-center gap-1.5 text-gray-600 dark:text-gray-400">
            <span className="inline-block size-2.5 rounded-full bg-[#3b82f6]" /> Featured
          </div>
          <div className="flex items-center gap-1.5 text-gray-600 dark:text-gray-400">
            <span className="inline-block size-2.5 rounded-full bg-[#f59e0b]" /> Premium
          </div>

          {/* Area boundary indicator */}
          {showAreas && (
            <div className="mt-1.5 flex items-center gap-1.5 text-gray-600 dark:text-gray-400">
              <span className="inline-block h-0.5 w-4 rounded bg-[#ea580c] dark:bg-[#fb923c]" />
              Area
            </div>
          )}

          {/* Landmark categories — shown only while their layer is on */}
          {showLandmarks.universities && (
            <div className="flex items-center gap-1.5 text-gray-600 dark:text-gray-400">
              <GraduationCap
                className={`size-3.5 ${darkMode ? "text-[#a78bfa]" : "text-[#7c3aed]"}`}
              />
              University
            </div>
          )}
          {showLandmarks.metro && (
            <div className="flex items-center gap-1.5 text-gray-600 dark:text-gray-400">
              <TrainFront
                className={`size-3.5 ${darkMode ? "text-[#2dd4bf]" : "text-[#0d9488]"}`}
              />
              Metro
            </div>
          )}
          {showLandmarks.metro && (
            <div className="flex items-center gap-1.5 text-gray-600 dark:text-gray-400">
              <span className="inline-block h-0.5 w-4 rounded bg-[#0d9488] dark:bg-[#2dd4bf]" />
              MRT Line 6
            </div>
          )}

          {/* Everyday landmark categories */}
          {(
            [
              ["hospital", "Hospital", Hospital],
              ["market", "Market", ShoppingBasket],
              ["park", "Park", TreePine],
              ["mosque", "Mosque", Church],
              ["bus_terminal", "Bus terminal", Bus],
            ] as const
          ).map(([kind, label, Icon]) =>
            showLandmarks[kind] ? (
              <div
                key={kind}
                className="flex items-center gap-1.5 text-gray-600 dark:text-gray-400"
              >
                <Icon
                  className="size-3.5"
                  style={{
                    color: darkMode
                      ? LANDMARK_KIND_META[kind].darkColor
                      : LANDMARK_KIND_META[kind].color,
                  }}
                />
                {label}
              </div>
            ) : null
          )}

          {/* Zoom-dependency hint */}
          {(() => {
            const everydayOn = (["hospital", "market", "park", "mosque", "bus_terminal"] as const)
              .filter((k) => showLandmarks[k])
              .map((k) => LANDMARK_KIND_META[k]);
            if (everydayOn.length === 0) return null;
            const minZoomNeeded = Math.min(...everydayOn.map((m) => m.minzoom));
            if (mapZoom >= minZoomNeeded) return null;
            return (
              <div className="mt-1 text-[10px] italic text-gray-400 dark:text-gray-500">
                Zoom in to see individual places
              </div>
            );
          })()}
        </>
      )}
    </div>
  );
}
