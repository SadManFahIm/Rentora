// Phase 7 — Interactive map view (MapLibre GL JS).
//
// The map is the discovery surface for the geo backend: every viewport change
// refetches rooms inside the visible bounding box (`bbox`), markers open the
// existing RoomModal, and landmarks (universities + metro stations) can be
// toggled as layers. A radius search lets tenants pick a point on the map
// (a university, metro station, or their office) and see rooms within N km.
import { useEffect, useMemo, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import type { StyleSpecification } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import {
  Crosshair,
  Landmark as LandmarkIcon,
  List as ListIcon,
  Map as MapIcon,
  TrainFront,
  Thermometer,
  Users as UsersIcon,
  X,
} from "lucide-react";
import { useLandmarks, useRooms } from "../../hooks/useRooms";
import RoomModal from "../../components/RoomModal/RoomModal";
import { Button } from "../../components/ui/button";
import { Badge } from "../../components/ui/badge";
import { useUiStore } from "../../stores/uiStore";
import type { Room } from "../../types";
import {
  avgPrice,
  buildBbox,
  landmarksToFeatureCollection,
  markerClassName,
  markerPrice,
  roomsToFeatureCollection,
  sortRoomsForList,
  tierColor,
  viewSummary,
} from "../../lib/mapUtils";
import { cn } from "../../lib/utils";

// Dhaka centre — the default viewport for first-time visitors.
const DHAKA_CENTER: [number, number] = [90.4125, 23.8103];
const DHAKA_ZOOM = 11.2;

// Key-free raster tiles (OSM/CARTO). Light/dark follow the app theme.
const TILE_LIGHT = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const TILE_DARK = "https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png";

const MAP_STYLE = (tiles: string): StyleSpecification => ({
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: [tiles],
      tileSize: 256,
      // CARTO dark tiles (used in dark mode) are OSM-derived; their own
      // tiles carry the attribution banner, so crediting OSM suffices.
      attribution: "© OpenStreetMap contributors",
      maxzoom: 19,
    },
  },
  layers: [{ id: "osm", type: "raster", source: "osm" }],
});

/** Debounce map-move refetches so panning doesn't hammer the API. */
function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(t);
  }, [value, delayMs]);
  return debounced;
}

type MapLayerId = "universities" | "metro";

export default function Map() {
  const darkMode = useUiStore((s) => s.darkMode);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markersRef = useRef<maplibregl.Marker[]>([]);
  // Live rooms for the once-per-map event handlers (see clustering effect).
  const roomsRef = useRef<Room[]>([]);
  // Guards the once-per-map registration of cluster click/hover handlers.
  const clusterHandlersRef = useRef<maplibregl.Map | null>(null);
  const [selectedRoom, setSelectedRoom] = useState<Room | null>(null);
  const [showLandmarks, setShowLandmarks] = useState<Record<MapLayerId, boolean>>({
    universities: true,
    metro: true,
  });
  const [heatmap, setHeatmap] = useState(false);
  const [clustering, setClustering] = useState(true);
  const [listOpen, setListOpen] = useState(false);
  const [activeRoomId, setActiveRoomId] = useState<number | null>(null);
  const [mapReady, setMapReady] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);

  // ---- radius search state --------------------------------------------
  const [radiusCenter, setRadiusCenter] = useState<{
    lat: number;
    lng: number;
    label: string;
  } | null>(null);
  const [radiusKm, setRadiusKm] = useState(2);
  const [viewbox, setViewbox] = useState<string | null>(null);

  // Debounced viewport: fires ~300ms after the user stops panning/zooming.
  const debouncedViewbox = useDebouncedValue(viewbox, 300);
  const debouncedRadiusCenter = useDebouncedValue(radiusCenter, 300);

  const filters = useMemo(() => {
    const f: {
      bbox?: string;
      nearLat?: number;
      nearLng?: number;
      radiusKm?: number;
    } = {};
    if (debouncedRadiusCenter) {
      f.nearLat = debouncedRadiusCenter.lat;
      f.nearLng = debouncedRadiusCenter.lng;
      f.radiusKm = radiusKm;
    } else if (debouncedViewbox) {
      f.bbox = debouncedViewbox;
    }
    return f;
  }, [debouncedViewbox, debouncedRadiusCenter, radiusKm]);

  const { data: rooms = [], isLoading } = useRooms(filters);
  const { data: landmarks = [] } = useLandmarks();
  roomsRef.current = rooms;

  // ---- map bootstrap ---------------------------------------------------
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: MAP_STYLE(darkMode ? TILE_DARK : TILE_LIGHT),
      center: DHAKA_CENTER,
      zoom: DHAKA_ZOOM,
      attributionControl: { compact: true },
    });
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl({ showCompass: true }), "top-right");
    map.addControl(
      new maplibregl.GeolocateControl({ positionOptions: { enableHighAccuracy: true } })
    );

    // Pan/zoom end -> update the bbox the room list is filtered by.
    const syncViewbox = () => {
      const b = map.getBounds();
      setViewbox(
        buildBbox({
          west: b.getWest(),
          south: b.getSouth(),
          east: b.getEast(),
          north: b.getNorth(),
        })
      );
    };

    map.on("load", () => {
      setMapReady(true);
      // Sync the viewport once the map has its initial position.
      syncViewbox();
    });
    map.on("moveend", syncViewbox);

    // Clicking empty map space clears the radius search and the active pin.
    map.on("click", (e: maplibregl.MapMouseEvent) => {
      if (e.originalEvent.target === map.getCanvas()) {
        setRadiusCenter(null);
        setActiveRoomId(null);
      }
    });

    map.on("error", () => {
      // Tiles can fail offline; don't let the whole page crash.
      setMapError("Map tiles could not be loaded — check your connection.");
    });

    return () => {
      markersRef.current.forEach((m) => m.remove());
      markersRef.current = [];
      map.remove();
      mapRef.current = null;
      // Force dependent effects (markers, layers, heatmap) to re-run against
      // the fresh map instance when the map is recreated (e.g. dark-mode
      // tile switch) — without this, mapReady stays true and the new map
      // would render with no markers until the next refetch.
      setMapReady(false);
    };
  }, [darkMode]);

  // ---- GeoJSON layers (landmarks + heatmap) ----------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;

    const addSourceLayer = (id: string, data: GeoJSON.FeatureCollection, paint: object) => {
      try {
        if (map.getSource(id)) {
          (map.getSource(id) as maplibregl.GeoJSONSource).setData(data);
        } else {
          map.addSource(id, { type: "geojson", data });
          map.addLayer({ id, type: "circle", source: id, paint });
        }
      } catch {
        // Source/layer already exists from a previous pass — no-op.
      }
    };

    const univ = landmarks.filter((l) => l.kind === "university");
    const metro = landmarks.filter((l) => l.kind === "metro");
    addSourceLayer("universities", landmarksToFeatureCollection(univ), {
      "circle-radius": 6,
      "circle-color": "#7c3aed",
      "circle-stroke-color": "#ffffff",
      "circle-stroke-width": 1.5,
      "circle-opacity": 0.9,
    });
    addSourceLayer("metro", landmarksToFeatureCollection(metro), {
      "circle-radius": 5,
      "circle-color": "#0d9488",
      "circle-stroke-color": "#ffffff",
      "circle-stroke-width": 1.5,
      "circle-opacity": 0.9,
    });
  }, [landmarks, mapReady]);

  // Layer visibility follows the toggles.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    (["universities", "metro"] as MapLayerId[]).forEach((id) => {
      if (map.getLayer(id))
        map.setLayoutProperty(id, "visibility", showLandmarks[id] ? "visible" : "none");
    });
  }, [showLandmarks, mapReady]);

  // ---- heatmap layer -----------------------------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const id = "price-heatmap";
    try {
      if (heatmap) {
        if (!map.getSource(id)) {
          map.addSource(id, { type: "geojson", data: roomsToFeatureCollection(rooms) });
          map.addLayer({
            id,
            type: "circle",
            source: id,
            paint: {
              "circle-radius": [
                "interpolate",
                ["linear"],
                ["get", "price"],
                5000,
                8,
                15000,
                16,
                30000,
                24,
              ],
              "circle-color": [
                "interpolate",
                ["linear"],
                ["get", "price"],
                5000,
                "#22c55e",
                15000,
                "#f59e0b",
                30000,
                "#ef4444",
              ],
              "circle-opacity": 0.45,
              "circle-stroke-color": "#ffffff",
              "circle-stroke-width": 1,
            },
          });
        } else {
          (map.getSource(id) as maplibregl.GeoJSONSource).setData(roomsToFeatureCollection(rooms));
        }
      } else if (map.getLayer(id)) {
        map.removeLayer(id);
        map.removeSource(id);
      }
    } catch {
      // Layer juggling during rapid toggle — safe to ignore.
    }
  }, [heatmap, rooms, mapReady]);

  // ---- custom price markers / clustered layer ------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;

    const CLUSTER_SOURCE = "rooms-clusters";
    const CLUSTER_LAYER = "rooms-clusters-layer";
    const CLUSTER_COUNT = "rooms-cluster-count";
    const UNCLUSTERED = "rooms-unclustered-point";

    // Escape user-generated text before it enters popup HTML — the backend
    // sanitizes titles, but defence-in-depth keeps stored-XSS out of popups.
    const esc = (s: string) =>
      s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

    const openRoom = (room: Room) => {
      setSelectedRoom(room);
      setActiveRoomId(room.id);
    };

    // ---- clustering mode: GeoJSON cluster source + layers ----
    if (clustering) {
      // Remove custom markers; the layers replace them.
      markersRef.current.forEach((m) => m.remove());
      markersRef.current = [];

      try {
        if (!map.getSource(CLUSTER_SOURCE)) {
          map.addSource(CLUSTER_SOURCE, {
            type: "geojson",
            data: roomsToFeatureCollection(rooms),
            cluster: true,
            clusterMaxZoom: 14,
            clusterRadius: 50,
          });
          map.addLayer({
            id: CLUSTER_LAYER,
            type: "circle",
            source: CLUSTER_SOURCE,
            filter: ["has", "point_count"],
            paint: {
              "circle-color": [
                "step",
                ["get", "point_count"],
                "#f97316",
                10,
                "#ea580c",
                50,
                "#c2410c",
              ],
              "circle-radius": ["step", ["get", "point_count"], 20, 10, 28, 50, 36],
              "circle-opacity": 0.9,
              "circle-stroke-color": "#ffffff",
              "circle-stroke-width": 2,
            },
          });
          map.addLayer({
            id: CLUSTER_COUNT,
            type: "symbol",
            source: CLUSTER_SOURCE,
            filter: ["has", "point_count"],
            layout: {
              "text-field": ["get", "point_count_abbreviated"],
              "text-size": 12,
              "text-font": ["DIN Offc Pro Medium", "Arial Unicode MS Bold"],
            },
            paint: { "text-color": "#ffffff" },
          });
          map.addLayer({
            id: UNCLUSTERED,
            type: "circle",
            source: CLUSTER_SOURCE,
            filter: ["!", ["has", "point_count"]],
            paint: {
              "circle-radius": 8,
              "circle-color": [
                "match",
                ["get", "tier"],
                "premium",
                "#f59e0b",
                "featured",
                "#3b82f6",
                "#ea580c",
              ],
              "circle-stroke-color": "#ffffff",
              "circle-stroke-width": 2,
            },
          });
        } else {
          (map.getSource(CLUSTER_SOURCE) as maplibregl.GeoJSONSource).setData(
            roomsToFeatureCollection(rooms)
          );
        }

        // Interactive handlers are registered ONCE per map instance.
        // MapLibre's .on() does not dedupe — the effect re-runs on every
        // rooms refetch, so re-registering would stack duplicate listeners.
        // Handlers read live data through roomsRef instead of the closure.
        if (clusterHandlersRef.current !== map) {
          clusterHandlersRef.current = map;

          // Cluster click -> zoom in on the cluster.
          map.on("click", CLUSTER_LAYER, (e) => {
            const feature = e.features?.[0];
            if (!feature) return;
            const clusterId = feature.properties?.cluster_id as number;
            (map.getSource(CLUSTER_SOURCE) as maplibregl.GeoJSONSource)
              .getClusterExpansionZoom(clusterId)
              .then((zoom) => {
                map.easeTo({
                  center: (feature.geometry as GeoJSON.Point).coordinates as [number, number],
                  zoom: zoom + 1,
                });
              });
          });

          // Unclustered point click -> open the room.
          map.on("click", UNCLUSTERED, (e) => {
            const feature = e.features?.[0];
            if (!feature) return;
            const roomId = feature.properties?.id as number;
            const room = roomsRef.current.find((r) => r.id === roomId);
            if (room) openRoom(room);
          });

          // Hover pointer for interactive layers.
          map.on("mouseenter", CLUSTER_LAYER, () => (map.getCanvas().style.cursor = "pointer"));
          map.on("mouseleave", CLUSTER_LAYER, () => (map.getCanvas().style.cursor = ""));
          map.on("mouseenter", UNCLUSTERED, () => (map.getCanvas().style.cursor = "pointer"));
          map.on("mouseleave", UNCLUSTERED, () => (map.getCanvas().style.cursor = ""));
        }
      } catch {
        // Layer juggling during rapid toggle — safe to ignore.
      }
      return;
    }

    // ---- marker mode: custom HTML price pins ----
    try {
      [CLUSTER_LAYER, CLUSTER_COUNT, UNCLUSTERED].forEach((id) => {
        if (map.getLayer(id)) map.removeLayer(id);
      });
      if (map.getSource(CLUSTER_SOURCE)) map.removeSource(CLUSTER_SOURCE);
    } catch {
      // no-op
    }

    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];

    rooms.forEach((room) => {
      if (!room.available) return;
      const el = document.createElement("button");
      el.className = markerClassName(room.tier);
      el.setAttribute("aria-label", `View ${room.name}`);
      el.setAttribute("data-room-id", String(room.id));
      el.innerHTML = markerPrice(room.price);

      const popup = new maplibregl.Popup({ offset: 22, closeButton: false, maxWidth: "260px" })
        .setHTML(`
        <div class="map-popup">
          <div class="map-popup__price">৳${room.price.toLocaleString()}<span>/mo</span></div>
          <div class="map-popup__name">${esc(room.name)}</div>
          <div class="map-popup__meta">${esc(room.area)} · ${esc(room.type)} · ★ ${room.rating} (${room.reviews})</div>
          <div class="map-popup__cta">View listing →</div>
        </div>
      `);

      const marker = new maplibregl.Marker({ element: el, anchor: "bottom" })
        .setLngLat([room.lng, room.lat])
        .setPopup(popup)
        .addTo(map);

      el.addEventListener("click", () => openRoom(room));
      markersRef.current.push(marker);
    });
  }, [rooms, mapReady, clustering]);

  // Keep the active room highlighted without re-creating all markers
  // (re-creating on activeRoomId change would detach the open popup).
  useEffect(() => {
    markersRef.current.forEach((m) => {
      const id = m.getElement().dataset.roomId;
      m.getElement().classList.toggle("map-marker--active", Number(id) === activeRoomId);
    });
  }, [activeRoomId, mapReady]);

  // ---- radius circle -------------------------------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const id = "radius-circle";
    try {
      if (radiusCenter) {
        if (!map.getSource(id)) {
          map.addSource(id, { type: "geojson", data: { type: "FeatureCollection", features: [] } });
          map.addLayer({
            id,
            type: "circle",
            source: id,
            paint: {
              // Draw the circle at the true on-screen radius: at zoom z the
              // metres-per-pixel ≈ 156543.03 · cos(lat) / 2^z, so a km-radius
              // becomes radiusKm·1000·2^z / (156543.03·cos(lat)) px. Dhaka is
              // ~23.8°N (cos ≈ 0.914); stop points evaluated at z=10 and z=16
              // let the exponential curve track it closely in between.
              "circle-radius": [
                "interpolate",
                ["exponential", 2],
                ["zoom"],
                10,
                (radiusKm * 1000 * 2 ** 10) / (156543.03 * 0.914),
                16,
                (radiusKm * 1000 * 2 ** 16) / (156543.03 * 0.914),
              ],
              "circle-color": "#3b82f6",
              "circle-opacity": 0.12,
              "circle-stroke-color": "#3b82f6",
              "circle-stroke-width": 2,
            },
          });
        }
        (map.getSource(id) as maplibregl.GeoJSONSource).setData({
          type: "FeatureCollection",
          features: [
            {
              type: "Feature",
              geometry: { type: "Point", coordinates: [radiusCenter.lng, radiusCenter.lat] },
              properties: {},
            },
          ],
        });
      } else if (map.getLayer(id)) {
        map.removeLayer(id);
        map.removeSource(id);
      }
    } catch {
      // no-op during rapid state changes
    }
  }, [radiusCenter, radiusKm, mapReady]);

  const counts = useMemo(() => {
    const total = rooms.length;
    const available = rooms.filter((r) => r.available).length;
    return { total, available, avg: avgPrice(rooms) };
  }, [rooms]);

  return (
    <div className="relative flex h-[calc(100vh-5rem)] min-h-[560px] w-full overflow-hidden">
      {/* Map area (collapses when the list panel is open on desktop) */}
      <div
        className={cn(
          "relative min-w-0 flex-1 transition-[width]",
          listOpen && "lg:max-w-[calc(100%-24rem)]"
        )}
      >
        {/* Map canvas — inline position/height overrides MapLibre's own
            `.maplibregl-map { position: relative }` rule, which would
            otherwise collapse the container to height 0 and render nothing. */}
        <div
          ref={containerRef}
          className="absolute inset-0"
          style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}
        />

        {/* Map error overlay */}
        {mapError && (
          <div className="absolute inset-x-0 top-4 z-20 mx-auto w-fit max-w-lg rounded-xl border border-red-200 bg-red-50 px-5 py-3 text-sm font-medium text-red-700 shadow-lg dark:border-red-800 dark:bg-red-950/60 dark:text-red-300">
            {mapError}
          </div>
        )}

        {/* Toolbar */}
        <div className="absolute left-4 top-4 z-10 flex max-w-[calc(100%-2rem)] flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2 rounded-xl border border-gray-200 bg-white/95 p-2 shadow-lg backdrop-blur dark:border-gray-800 dark:bg-gray-900/95">
            <Button
              variant="ghost"
              size="sm"
              className={cn(
                "gap-1.5 rounded-lg",
                showLandmarks.universities &&
                  "bg-violet-50 text-violet-700 dark:bg-violet-950/40 dark:text-violet-300"
              )}
              onClick={() => setShowLandmarks((s) => ({ ...s, universities: !s.universities }))}
            >
              <LandmarkIcon className="size-4" /> Universities
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className={cn(
                "gap-1.5 rounded-lg",
                showLandmarks.metro &&
                  "bg-teal-50 text-teal-700 dark:bg-teal-950/40 dark:text-teal-300"
              )}
              onClick={() => setShowLandmarks((s) => ({ ...s, metro: !s.metro }))}
            >
              <TrainFront className="size-4" /> Metro
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className={cn(
                "gap-1.5 rounded-lg",
                heatmap && "bg-orange-50 text-orange-700 dark:bg-orange-950/40 dark:text-orange-300"
              )}
              onClick={() => setHeatmap((h) => !h)}
            >
              <Thermometer className="size-4" /> Price heatmap
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className={cn(
                "gap-1.5 rounded-lg",
                clustering && "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200"
              )}
              onClick={() => setClustering((c) => !c)}
            >
              <UsersIcon className="size-4" /> {clustering ? "Clustered" : "Pins"}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className={cn(
                "gap-1.5 rounded-lg",
                listOpen && "bg-blue-50 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300"
              )}
              onClick={() => setListOpen((o) => !o)}
            >
              <ListIcon className="size-4" /> List
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
            <div className="flex items-center gap-2">
              <input
                type="range"
                min={0.5}
                max={5}
                step={0.5}
                value={radiusKm}
                onChange={(e) => setRadiusKm(Number(e.target.value))}
                className="h-2 w-full cursor-pointer accent-blue-600"
                aria-label="Search radius in km"
              />
              <Button
                variant="outline"
                size="sm"
                className="shrink-0 rounded-lg text-xs"
                onClick={() => setRadiusCenter(null)}
              >
                Clear
              </Button>
            </div>
          </div>

          {/* Landmark quick-pick chips */}
          {!radiusCenter && (
            <div className="flex max-w-sm flex-wrap gap-1.5">
              {landmarks
                .filter((l) => l.kind === "university")
                .slice(0, 6)
                .map((l) => (
                  <button
                    key={l.key}
                    onClick={() => {
                      setRadiusCenter({ lat: l.lat, lng: l.lng, label: l.name });
                      mapRef.current?.flyTo({ center: [l.lng, l.lat], zoom: 13 });
                    }}
                    className="rounded-full border border-gray-200 bg-white/95 px-3 py-1 text-xs font-medium text-gray-700 shadow-sm backdrop-blur transition-colors hover:border-violet-300 hover:bg-violet-50 hover:text-violet-700 dark:border-gray-700 dark:bg-gray-900/95 dark:text-gray-300 dark:hover:border-violet-600 dark:hover:bg-violet-950/40 dark:hover:text-violet-300"
                  >
                    🎓 {l.name}
                  </button>
                ))}
            </div>
          )}
        </div>

        {/* Loading badge */}
        {isLoading && (
          <div className="absolute right-4 top-4 z-10">
            <Badge className="animate-pulse bg-white/90 text-gray-700 shadow dark:bg-gray-900/90 dark:text-gray-300">
              Loading rooms…
            </Badge>
          </div>
        )}

        {/* Room count summary */}
        <div className="absolute bottom-4 left-4 z-10 flex items-center gap-2">
          <Badge className="gap-1.5 bg-white/95 px-3 py-1.5 text-sm shadow dark:bg-gray-900/95">
            <MapIcon className="size-3.5" />
            {counts.available} rooms in view
            {counts.avg != null && (
              <span className="text-gray-500 dark:text-gray-400">
                · avg ৳{counts.avg.toLocaleString()}
              </span>
            )}
          </Badge>
        </div>

        {/* Legend */}
        <div className="absolute bottom-4 right-4 z-10 hidden rounded-lg border border-gray-200 bg-white/95 px-3 py-2 text-xs shadow backdrop-blur sm:block dark:border-gray-800 dark:bg-gray-900/95">
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
          <div className="mt-1.5 flex items-center gap-1.5 text-gray-600 dark:text-gray-400">
            <span className="inline-block size-2.5 rounded-full bg-[#7c3aed]" /> University
          </div>
          <div className="flex items-center gap-1.5 text-gray-600 dark:text-gray-400">
            <span className="inline-block size-2.5 rounded-full bg-[#0d9488]" /> Metro
          </div>
        </div>

        {selectedRoom && <RoomModal room={selectedRoom} onClose={() => setSelectedRoom(null)} />}
      </div>

      {/* Sidebar list panel (desktop) — viewport-synced room list */}
      <aside
        className={cn(
          "hidden w-96 shrink-0 flex-col border-l border-gray-200 bg-card lg:flex dark:border-gray-800",
          !listOpen && "hidden lg:hidden"
        )}
      >
        <MapSidebar
          rooms={rooms}
          loading={isLoading}
          activeId={activeRoomId}
          onSelect={(room) => {
            setActiveRoomId(room.id);
            setListOpen(true);
            mapRef.current?.flyTo({
              center: [room.lng, room.lat],
              zoom: Math.max(mapRef.current.getZoom(), 14),
            });
            setSelectedRoom(room);
          }}
          onClose={() => setListOpen(false)}
        />
      </aside>

      {/* Mobile bottom sheet */}
      {listOpen && (
        <div className="absolute inset-x-0 bottom-0 z-30 max-h-[45%] overflow-y-auto rounded-t-2xl border-t border-gray-200 bg-card shadow-2xl lg:hidden dark:border-gray-800">
          <MapSidebar
            rooms={rooms}
            loading={isLoading}
            activeId={activeRoomId}
            onSelect={(room) => {
              setActiveRoomId(room.id);
              setSelectedRoom(room);
            }}
            onClose={() => setListOpen(false)}
          />
        </div>
      )}
    </div>
  );
}

interface MapSidebarProps {
  rooms: Room[];
  loading: boolean;
  activeId: number | null;
  onSelect: (room: Room) => void;
  onClose: () => void;
}

function MapSidebar({ rooms, loading, activeId, onSelect, onClose }: MapSidebarProps) {
  const sorted = useMemo(() => sortRoomsForList(rooms), [rooms]);
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3 dark:border-gray-800">
        <h3 className="font-display text-sm font-bold text-foreground">{viewSummary(rooms)}</h3>
        <Button
          variant="ghost"
          size="icon"
          className="size-7 rounded-lg"
          onClick={onClose}
          aria-label="Close list"
        >
          <X className="size-4" />
        </Button>
      </div>
      <div className="flex-1 overflow-y-auto p-2">
        {loading && rooms.length === 0 ? (
          <p className="px-3 py-6 text-center text-sm text-gray-500 dark:text-gray-400">Loading…</p>
        ) : rooms.length === 0 ? (
          <p className="px-3 py-6 text-center text-sm text-gray-500 dark:text-gray-400">
            No rooms in this area — pan the map or widen your search.
          </p>
        ) : (
          sorted.map((room) => (
            <button
              key={room.id}
              onClick={() => onSelect(room)}
              className={cn(
                "mb-1.5 flex w-full items-center gap-3 rounded-xl border p-2.5 text-left transition-colors",
                activeId === room.id
                  ? "border-orange-400 bg-orange-50 dark:border-orange-600 dark:bg-orange-950/40"
                  : "border-transparent hover:border-gray-200 hover:bg-gray-50 dark:hover:border-gray-700 dark:hover:bg-gray-800/60"
              )}
            >
              <div
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-xs font-bold text-white"
                style={{ backgroundColor: tierColor(room.tier) }}
              >
                {markerPrice(room.price)}
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-semibold text-foreground">{room.name}</div>
                <div className="truncate text-xs text-gray-500 dark:text-gray-400">
                  {room.area} · {room.type} · ★ {room.rating} ({room.reviews})
                </div>
              </div>
              <div className="shrink-0 text-sm font-bold text-orange-600">
                ৳{room.price.toLocaleString()}
              </div>
            </button>
          ))
        )}
      </div>
    </div>
  );
}
