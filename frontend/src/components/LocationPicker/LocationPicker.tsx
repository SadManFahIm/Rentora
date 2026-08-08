// Listing Location Picker — a small MapLibre map the landlord clicks to set
// a room's coordinates. Used inside the create-listing form.
import { useEffect, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import type { StyleSpecification } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { Crosshair, LocateFixed, MapPin } from "lucide-react";
import { useUiStore } from "../../stores/uiStore";
import { cn } from "../../lib/utils";

const DHAKA: [number, number] = [90.4125, 23.8103];

const MAP_STYLE = (tiles: string): StyleSpecification => ({
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: [tiles],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors",
      maxzoom: 19,
    },
  },
  layers: [{ id: "osm", type: "raster", source: "osm" }],
});

interface LocationPickerProps {
  value: { lat: number; lng: number } | null;
  onChange: (point: { lat: number; lng: number }) => void;
  /** Form-friendly label above the map. */
  label?: string;
}

export default function LocationPicker({ value, onChange, label }: LocationPickerProps) {
  const darkMode = useUiStore((s) => s.darkMode);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markerRef = useRef<maplibregl.Marker | null>(null);
  const [locating, setLocating] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);

  // Bootstrap the map once; recreate only when the theme's tile set changes.
  useEffect(() => {
    if (!containerRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: MAP_STYLE(
        darkMode
          ? "https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png"
          : "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
      ),
      center: value ? [value.lng, value.lat] : DHAKA,
      zoom: value ? 14 : 11.5,
      attributionControl: { compact: true },
      interactive: true,
    });
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

    map.on("load", () => {
      if (value) updateMarker(map, value);
    });

    // Click sets the listing location.
    map.on("click", (e: maplibregl.MapMouseEvent) => {
      const point = { lat: e.lngLat.lat, lng: e.lngLat.lng };
      updateMarker(map, point);
      onChange(point);
    });

    map.on("error", () => setMapError("Map tiles could not be loaded."));

    return () => {
      map.remove();
      mapRef.current = null;
      markerRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [darkMode]);

  function updateMarker(map: maplibregl.Map, point: { lat: number; lng: number }) {
    if (markerRef.current) markerRef.current.remove();
    const el = document.createElement("div");
    el.className = "map-marker";
    el.style.minWidth = "26px";
    el.style.height = "20px";
    el.style.fontSize = "10px";
    el.textContent = "📍";
    markerRef.current = new maplibregl.Marker({ element: el, anchor: "bottom" })
      .setLngLat([point.lng, point.lat])
      .addTo(map);
  }

  const useMyLocation = () => {
    if (!navigator.geolocation) return;
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocating(false);
        const point = { lat: pos.coords.latitude, lng: pos.coords.longitude };
        updateMarker(mapRef.current!, point);
        mapRef.current?.flyTo({ center: [point.lng, point.lat], zoom: 14 });
        onChange(point);
      },
      () => setLocating(false),
      { enableHighAccuracy: true, timeout: 8000 }
    );
  };

  return (
    <div className="w-full">
      {label && (
        <label className="mb-1.5 flex items-center gap-1.5 text-sm font-medium text-foreground">
          <MapPin className="size-4 text-orange-600" /> {label}
        </label>
      )}
      <div className="relative overflow-hidden rounded-xl border border-gray-200 dark:border-gray-800">
        <div
          ref={containerRef}
          className="h-64 w-full"
          style={{ minHeight: "256px", width: "100%" }}
        />
        {mapError && (
          <div className="absolute inset-x-0 top-2 z-10 mx-auto w-fit rounded-lg bg-red-50 px-3 py-1.5 text-xs font-medium text-red-700 dark:bg-red-950/60 dark:text-red-300">
            {mapError}
          </div>
        )}
        {/* Click hint */}
        <div className="pointer-events-none absolute bottom-3 left-1/2 z-10 -translate-x-1/2 rounded-full bg-black/60 px-3.5 py-1.5 text-xs font-medium text-white backdrop-blur">
          Click the map to pin your listing location
        </div>
      </div>

      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-400">
          <Crosshair className="size-3.5" />
          {value ? (
            <span className="font-semibold text-foreground">
              {value.lat.toFixed(5)}, {value.lng.toFixed(5)}
            </span>
          ) : (
            <span>No location picked yet</span>
          )}
        </div>
        <button
          type="button"
          onClick={useMyLocation}
          disabled={locating}
          className={cn(
            "flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-semibold text-foreground transition-colors",
            "hover:border-orange-300 hover:bg-orange-50 hover:text-orange-700",
            "dark:border-gray-700 dark:hover:border-orange-600 dark:hover:bg-orange-950/40 dark:hover:text-orange-300",
            locating && "opacity-60"
          )}
        >
          <LocateFixed className={cn("size-3.5", locating && "animate-pulse")} />
          {locating ? "Locating…" : "Use my location"}
        </button>
      </div>
    </div>
  );
}
