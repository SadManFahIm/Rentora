// Phase 7 — Interactive map view (MapLibre GL JS).
//
// The map is the discovery surface for the geo backend: every viewport change
// refetches rooms inside the visible bounding box (`bbox`), markers open the
// existing RoomModal, and landmarks (universities + metro stations) can be
// toggled as layers. A radius search lets tenants pick a point on the map
// (a university, metro station, or their office) and see rooms within N km.
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import * as maplibregl from "maplibre-gl";
import type { StyleSpecification } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import {
  Crosshair,
  Footprints,
  GraduationCap,
  Landmark as LandmarkIcon,
  List as ListIcon,
  Map as MapIcon,
  MapPin,
  Search,
  TrainFront,
  Thermometer,
  Users as UsersIcon,
  X,
} from "lucide-react";
import { useGeocode, useLandmarks, useMapSummary, useRooms } from "../../hooks/useRooms";
import RoomModal from "../../components/RoomModal/RoomModal";
import { Button } from "../../components/ui/button";
import { Badge } from "../../components/ui/badge";
import { useUiStore } from "../../stores/uiStore";
import type { GeocodeSuggestion, Room } from "../../types";
import {
  avgPrice,
  buildBbox,
  formatDistance,
  formatTravelTime,
  haversineKm,
  landmarkToFeature,
  landmarksToFeatureCollection,
  markerClassName,
  markerPrice,
  metroRouteFeatureCollection,
  quantizeBounds,
  roomsToFeatureCollection,
  sortRoomsForList,
  tierColor,
  travelIsochrones,
  viewSummary,
} from "../../lib/mapUtils";
import { cn } from "../../lib/utils";

// Dhaka centre — the default viewport for first-time visitors.
const DHAKA_CENTER: [number, number] = [90.4125, 23.8103];
const DHAKA_ZOOM = 11.2;

// Key-free raster tiles (OSM/CARTO). Light/dark follow the app theme.
const TILE_LIGHT = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const TILE_DARK = "https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png";

// Dimmed OSM raster fallback for dark mode. CARTO's CDN is occasionally
// unreachable (some ISPs/regions), which would leave a black, unreadable
// map — so when dark tiles fail we re-render the map on plain OSM tiles
// darkened with raster paint properties (labels stay visible).
const MAP_STYLE = (tiles: string, dimForDark: boolean): StyleSpecification => ({
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
  layers: [
    {
      id: "osm",
      type: "raster",
      source: "osm",
      paint: dimForDark
        ? {
            "raster-brightness-min": 0.02,
            "raster-brightness-max": 0.42,
            "raster-saturation": -0.85,
            "raster-contrast": 0.25,
          }
        : {},
    },
  ],
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
  const [showTravel, setShowTravel] = useState(false);
  const [activeRoomId, setActiveRoomId] = useState<number | null>(null);

  // ---- street search / autocomplete state --------------------------------
  const [searchQuery, setSearchQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [activeSuggestion, setActiveSuggestion] = useState(0);
  const searchInputRef = useRef<HTMLInputElement | null>(null);
  const [mapReady, setMapReady] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);
  // When dark tiles (CARTO CDN) fail to load, fall back to dimmed OSM tiles
  // so the map stays readable instead of going black.
  const [darkTileFallback, setDarkTileFallback] = useState(false);

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
  // Debounced street-search query — autocomplete fires 250ms after typing stops.
  const debouncedSearchQuery = useDebouncedValue(searchQuery, 250);

  const { data: suggestions = [], isFetching: searching } = useGeocode(debouncedSearchQuery);

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
  // Authoritative room counts for the badge (COUNT/AVG server-side — the
  // paginated list caps at one page, so client-side counting undercounts).
  const { data: summary } = useMapSummary(filters);
  roomsRef.current = rooms;

  // ---- map bootstrap ---------------------------------------------------
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const tiles = darkMode ? (darkTileFallback ? TILE_LIGHT : TILE_DARK) : TILE_LIGHT;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: MAP_STYLE(tiles, darkMode && darkTileFallback),
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
    // Quantized outward to ~100 m so micro-pans between two positions that
    // are effectively the same viewport hit the React Query cache instead of
    // firing a fresh refetch (the bbox cache), while never shrinking below
    // the visible area (edge rooms can't be dropped from results).
    const syncViewbox = () => {
      const b = map.getBounds();
      setViewbox(
        buildBbox(
          quantizeBounds({
            west: b.getWest(),
            south: b.getSouth(),
            east: b.getEast(),
            north: b.getNorth(),
          })
        )
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

    map.on("error", (e) => {
      // Raster tiles sometimes 404 for a single tile (benign). Only treat
      // real fetch/network failures as a problem.
      const msg = (e?.error as Error | undefined)?.message ?? "";
      if (/Failed to fetch|NetworkError|timeout|ERR_/i.test(msg)) {
        if (darkMode && !darkTileFallback) {
          // CARTO dark CDN unreachable — re-render on dimmed OSM tiles.
          setDarkTileFallback(true);
        } else {
          setMapError("Map tiles could not be loaded — check your connection.");
        }
      }
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
  }, [darkMode, darkTileFallback]);

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

  // ---- metro route corridor -----------------------------------------------
  // A polyline threading the MRT Line 6 stations (Uttara → Motijheel) so the
  // rail corridor is visible, not just isolated station dots. Follows the
  // Metro toggle; also shown while the travel overlay is active so tenants
  // can see which corridor they'd ride to/from their radius search.
  //
  // Layering: the white casing is added FIRST (bottom) and the teal core
  // SECOND (top) with a `line-gap-width` — the transparent gap around the
  // core lets the casing show through, so the corridor reads as a teal line
  // with a white halo on both light and dark basemaps. (Adding the casing
  // on top would have hidden the core entirely; ordering matters.)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const id = "metro-route";
    const casingId = `${id}-casing`;
    try {
      const metro = landmarks.filter((l) => l.kind === "metro");
      const data = metroRouteFeatureCollection(metro);
      const visible = showLandmarks.metro || showTravel;
      const setVisibility = () => {
        // Update BOTH layers on every run — the existing-layer branch below
        // re-runs when the Metro toggle or travel overlay flips, and the
        // casing must stay in sync with the core.
        [id, casingId].forEach((l) => {
          if (map.getLayer(l)) map.setLayoutProperty(l, "visibility", visible ? "visible" : "none");
        });
      };
      if (map.getLayer(id)) {
        setVisibility();
        (map.getSource(id) as maplibregl.GeoJSONSource).setData(data);
      } else if (data.features.length > 0) {
        map.addSource(id, { type: "geojson", data });
        // Casing first (bottom), then core on top with a gap to reveal it.
        map.addLayer({
          id: casingId,
          type: "line",
          source: id,
          layout: { "line-cap": "round", "line-join": "round" },
          paint: {
            "line-color": "#ffffff",
            "line-width": 8,
            "line-opacity": 0.55,
          },
        });
        map.addLayer({
          id,
          type: "line",
          source: id,
          layout: { "line-cap": "round", "line-join": "round" },
          paint: {
            "line-color": "#0d9488",
            "line-width": 4,
            "line-opacity": 0.9,
            "line-gap-width": 3,
          },
        });
        setVisibility();
      }
    } catch {
      // Rapid theme/state changes during layer juggling — safe to ignore.
    }
  }, [landmarks, mapReady, showLandmarks.metro, showTravel]);

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

      const distanceLine =
        room.distanceKm != null
          ? `<div class="map-popup__dist">📍 ${formatDistance(room.distanceKm)} away · ${formatTravelTime(room.distanceKm)}</div>`
          : "";
      const popup = new maplibregl.Popup({ offset: 22, closeButton: false, maxWidth: "260px" })
        .setHTML(`
        <div class="map-popup">
          <div class="map-popup__price">৳${room.price.toLocaleString()}<span>/mo</span></div>
          <div class="map-popup__name">${esc(room.name)}</div>
          <div class="map-popup__meta">${esc(room.area)} · ${esc(room.type)} · ★ ${room.rating} (${room.reviews})</div>
          ${distanceLine}
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

  // ---- travel-time overlay -------------------------------------------------
  // Walking isochrone bands (10/20/30 min) around the radius-search centre,
  // so tenants see how far they can get on foot — useful when comparing
  // "how close to the university/office" a listing really is. Works in both
  // light and dark themes (semi-transparent fills + stroked rims).
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const id = "travel-bands";
    const bandLayerIds = [0, 1, 2].map((i) => `${id}-${i}`);
    const removeAll = () => {
      bandLayerIds.forEach((l) => {
        if (map.getLayer(l)) map.removeLayer(l);
      });
      if (map.getSource(id)) map.removeSource(id);
    };
    try {
      const active = showTravel && radiusCenter;
      if (active) {
        const bands = travelIsochrones(radiusCenter);
        if (!map.getSource(id)) {
          map.addSource(id, { type: "geojson", data: { type: "FeatureCollection", features: [] } });
          // Insert below the room markers/cluster layers so the translucent
          // bands tint the basemap, not the pins on top of it.
          const beforeId = map.getLayer("rooms-clusters-layer")
            ? "rooms-clusters-layer"
            : undefined;
          bands.forEach((band, i) => {
            map.addLayer(
              {
                id: `${id}-${i}`,
                type: "fill",
                source: id,
                filter: ["==", ["get", "band"], i],
                paint: {
                  "fill-color": band.color,
                  "fill-opacity": 0.1,
                  "fill-outline-color": band.color,
                },
              },
              beforeId
            );
          });
        }
        (map.getSource(id) as maplibregl.GeoJSONSource).setData({
          type: "FeatureCollection",
          features: bands.map((band, i) => ({
            ...band.feature,
            properties: { band: i },
          })),
        });

        // Metro stations within a 30-minute walk of the search point get a
        // highlighted ring — the stations a tenant could actually reach on
        // foot, feeding the "which line do I ride from here?" story.
        const reachId = "metro-reach";
        const reachable = landmarks
          .filter((l) => l.kind === "metro")
          .filter((l) => haversineKm(radiusCenter.lat, radiusCenter.lng, l.lat, l.lng) <= 2.25) // ~30 min walk
          .map(landmarkToFeature);
        if (!map.getSource(reachId)) {
          map.addSource(reachId, {
            type: "geojson",
            data: { type: "FeatureCollection", features: [] },
          });
          map.addLayer({
            id: reachId,
            type: "circle",
            source: reachId,
            paint: {
              "circle-radius": 12,
              "circle-color": "#0d9488",
              "circle-stroke-color": "#ffffff",
              "circle-stroke-width": 2.5,
              "circle-opacity": 0.9,
            },
          });
        }
        (map.getSource(reachId) as maplibregl.GeoJSONSource).setData({
          type: "FeatureCollection",
          features: reachable,
        });
      } else {
        removeAll();
        if (map.getLayer("metro-reach")) {
          map.removeLayer("metro-reach");
          map.removeSource("metro-reach");
        }
      }
    } catch {
      // no-op during rapid state changes
    }
  }, [showTravel, radiusCenter, mapReady, landmarks]);

  // Room-count badge: prefer the authoritative server summary (COUNT/AVG over
  // every row in view, not just page 1); fall back to the client-side list
  // while the summary request is in flight or when it isn't available.
  const counts = useMemo(() => {
    const total = summary?.total ?? rooms.length;
    const available = summary?.available ?? rooms.filter((r) => r.available).length;
    const avg = summary?.avg_price ?? avgPrice(rooms);
    return { total, available, avg: avg != null ? Math.round(avg) : null };
  }, [rooms, summary]);

  // ---- street search handlers --------------------------------------------
  const pickSuggestion = (s: GeocodeSuggestion) => {
    setSearchQuery(s.label);
    setSearchOpen(false);
    setRadiusCenter({ lat: s.lat, lng: s.lng, label: s.label });
    mapRef.current?.flyTo({ center: [s.lng, s.lat], zoom: 14 });
  };

  const onSearchKeyDown = (e: ReactKeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Escape") {
      setSearchOpen(false);
      return;
    }
    if (e.key === "Enter") {
      const hit = suggestions[activeSuggestion] ?? suggestions[0];
      if (hit) {
        e.preventDefault();
        pickSuggestion(hit);
      }
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveSuggestion((i) => Math.min(i + 1, Math.max(suggestions.length - 1, 0)));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveSuggestion((i) => Math.max(i - 1, 0));
    }
  };

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

        {/* Street search + autocomplete */}
        <div className="absolute left-1/2 top-4 z-20 w-[min(22rem,calc(100%-2rem))] -translate-x-1/2">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-gray-400 dark:text-gray-500" />
            <input
              ref={searchInputRef}
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setSearchOpen(true);
                setActiveSuggestion(0);
              }}
              onFocus={() => setSearchOpen(true)}
              onBlur={() => setTimeout(() => setSearchOpen(false), 150)}
              onKeyDown={onSearchKeyDown}
              placeholder="Search streets, areas, stations…"
              aria-label="Search for a street, area or station"
              className="h-11 w-full rounded-xl border border-gray-200 bg-white/95 pl-10 pr-9 text-sm shadow-lg backdrop-blur transition-colors placeholder:text-gray-400 focus:border-violet-400 focus:outline-none focus:ring-2 focus:ring-violet-200 dark:border-gray-700 dark:bg-gray-900/95 dark:placeholder:text-gray-500 dark:focus:border-violet-500 dark:focus:ring-violet-900"
            />
            {searchQuery && (
              <button
                onClick={() => {
                  setSearchQuery("");
                  setSearchOpen(false);
                  searchInputRef.current?.focus();
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
                  No places found — try “Gulshan”, “Mirpur Road” or “Shahbagh”.
                </div>
              ) : (
                <ul role="listbox" aria-label="Search suggestions">
                  {suggestions.map((s, i) => (
                    <li key={s.key}>
                      <button
                        role="option"
                        aria-selected={i === activeSuggestion}
                        onMouseEnter={() => setActiveSuggestion(i)}
                        onClick={() => pickSuggestion(s)}
                        className={cn(
                          "flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm transition-colors",
                          i === activeSuggestion
                            ? "bg-violet-50 dark:bg-violet-950/40"
                            : "hover:bg-gray-50 dark:hover:bg-gray-800/60"
                        )}
                      >
                        <SuggestionIcon kind={s.kind} />
                        <span className="min-w-0 flex-1 truncate text-foreground">{s.label}</span>
                        <span className="shrink-0 text-[11px] font-medium uppercase tracking-wide text-gray-400 dark:text-gray-500">
                          {s.kind}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>

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
                showTravel && "bg-teal-50 text-teal-700 dark:bg-teal-950/40 dark:text-teal-300"
              )}
              disabled={!radiusCenter}
              onClick={() => setShowTravel((t) => !t)}
            >
              <Footprints className="size-4" /> Travel
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
            {showTravel && radiusCenter && (
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

        {/* Room count summary — authoritative server count (not capped by pagination) */}
        <div className="absolute bottom-4 left-4 z-10 flex items-center gap-2">
          <Badge className="gap-1.5 bg-white/95 px-3 py-1.5 text-sm shadow dark:bg-gray-900/95">
            <MapIcon className="size-3.5" />
            {counts.available} of {counts.total} rooms in view
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
          <div className="flex items-center gap-1.5 text-gray-600 dark:text-gray-400">
            <span className="inline-block h-0.5 w-4 rounded bg-[#0d9488]" /> MRT Line 6
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

function SuggestionIcon({ kind }: { kind: GeocodeSuggestion["kind"] }) {
  const cls = "size-4 shrink-0";
  switch (kind) {
    case "university":
      return <GraduationCap className={cn(cls, "text-violet-600 dark:text-violet-400")} />;
    case "metro":
      return <TrainFront className={cn(cls, "text-teal-600 dark:text-teal-400")} />;
    case "area":
      return <MapPin className={cn(cls, "text-orange-600 dark:text-orange-400")} />;
    default:
      return <MapPin className={cn(cls, "text-blue-600 dark:text-blue-400")} />;
  }
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
                  {room.distanceKm != null && (
                    <>
                      {" "}
                      ·{" "}
                      <span className="text-teal-600 dark:text-teal-400">
                        {formatDistance(room.distanceKm)} · {formatTravelTime(room.distanceKm)}
                      </span>
                    </>
                  )}
                </div>
              </div>
              <div className="shrink-0 text-right text-sm font-bold text-orange-600">
                ৳{room.price.toLocaleString()}
              </div>
            </button>
          ))
        )}
      </div>
    </div>
  );
}
