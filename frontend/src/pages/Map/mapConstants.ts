/**
 * Map constants — shared across map hooks, layers, and components.
 *
 * Extracted from the monolithic Map.tsx to keep the main component focused
 * on orchestration while constants, styles, and types live in a single
 * importable module.
 */

import type { StyleSpecification } from "maplibre-gl";

// Dhaka centre — the default viewport for first-time visitors.
export const DHAKA_CENTER: [number, number] = [90.4125, 23.8103];
export const DHAKA_ZOOM = 11.2;

// Key-free raster tiles (OSM/CARTO). Light/dark follow the app theme.
export const TILE_LIGHT = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
export const TILE_DARK = "https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png";

/**
 * Raster basemap style.
 * - "light": plain OSM tiles.
 * - "dark": CARTO dark tiles with a gentle brightness/contrast lift.
 * - "dark-fallback": dimmed OSM tiles when CARTO CDN is unreachable.
 */
export type RasterMode = "light" | "dark" | "dark-fallback";

export const MAP_STYLE = (tiles: string, mode: RasterMode): StyleSpecification => ({
  version: 8,
  glyphs: "https://fonts.openmaptiles.org/{fontstack}/{range}.pbf",
  sources: {
    osm: {
      type: "raster",
      tiles: [tiles],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors",
      maxzoom: 19,
    },
  },
  layers: [
    {
      id: "osm",
      type: "raster",
      source: "osm",
      paint:
        mode === "dark"
          ? {
              "raster-brightness-min": 0.2,
              "raster-brightness-max": 0.85,
              "raster-saturation": 0.2,
              "raster-contrast": 0.2,
            }
          : mode === "dark-fallback"
            ? {
                "raster-brightness-min": 0.12,
                "raster-brightness-max": 0.68,
                "raster-saturation": -0.4,
                "raster-contrast": 0.25,
              }
            : {},
    },
  ],
});
