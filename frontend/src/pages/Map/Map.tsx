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
import { useSearchParams } from "react-router-dom";
import * as maplibregl from "maplibre-gl";
import type { StyleSpecification } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
// MapLibre v6 loads its worker via `new URL('./maplibre-gl-worker.mjs',
// import.meta.url)` — a path Vite/Rollup does NOT emit for node_modules libs,
// so the Worker would 404 (SPA fallback) and the map silently degrade to a
// main-thread mode where symbol TEXT never renders (area labels, cluster
// counts) and sources never report loaded. A plain `?url` copy is also
// insufficient: v6's worker is split — it imports `./maplibre-gl-shared.mjs`,
// which must ship alongside it. `?worker&url` makes Vite BUNDLE the worker
// and its imports into one self-contained file, and returns its URL — the
// correct worker for both dev and production builds.
import maplibreWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import {
  Bus,
  Check,
  Church,
  Crosshair,
  Footprints,
  GraduationCap,
  Hospital,
  Landmark as LandmarkIcon,
  List as ListIcon,
  Map as MapIcon,
  MapPin,
  Search,
  Share2,
  ShoppingBasket,
  Sparkles,
  Thermometer,
  TrainFront,
  TreePine,
  Users as UsersIcon,
  X,
} from "lucide-react";
import {
  useAreaBoundaries,
  useGeocode,
  useLandmarks,
  useMapSummary,
  useRooms,
} from "../../hooks/useRooms";
import RoomModal from "../../components/RoomModal/RoomModal";
import MapIntelPanel, { type MapIntelMode } from "../../components/MapIntelPanel/MapIntelPanel";
import { useValueScores } from "../../hooks/useMapIntel";
import { Button } from "../../components/ui/button";
import { Badge } from "../../components/ui/badge";
import { useUiStore } from "../../stores/uiStore";
import type { AreaKind, GeocodeSuggestion, LandmarkKind, Room } from "../../types";
import {
  areaBoundaryFillOpacity,
  areaBoundaryLineColor,
  areaStats,
  AREA_LABEL_MINZOOM,
  boundaryLabelsToFeatureCollection,
  heatmapPopupHtml,
  isochronePopupHtml,
  isochroneStats,
  landmarkMinzoom,
  landmarkPopupHtml,
  LANDMARK_KIND_META,
  metroRoutePopupHtml,
  nearbyLandmarkChipsHtml,
  nearbyStats,
  THEME_PAINTS,
  themePaintValue,
  TRAVEL_BAND_DARK_OPACITY,
  TRAVEL_BAND_LIGHT_OPACITY,
} from "../../lib/mapInteractions";
import {
  avgPrice,
  buildBbox,
  buildMapViewUrl,
  directionsUrl,
  formatDistance,
  formatDriveTime,
  formatTravelTime,
  haversineKm,
  landmarkToFeature,
  landmarksToFeatureCollection,
  markerClassName,
  markerPrice,
  metroRouteFeatureCollection,
  parseMapViewUrl,
  quantizeBounds,
  roomsToFeatureCollection,
  sortRoomsForList,
  tierColor,
  travelIsochrones,
  viewSummary,
  type TravelMode,
} from "../../lib/mapUtils";
import { cn } from "../../lib/utils";

// Dhaka centre — the default viewport for first-time visitors.
const DHAKA_CENTER: [number, number] = [90.4125, 23.8103];
const DHAKA_ZOOM = 11.2;

// Key-free raster tiles (OSM/CARTO). Light/dark follow the app theme.
// Raster is used deliberately over a vector style: vector tile CDNs
// (e.g. OpenFreeMap) serve their .pbf through a redirect that some networks
// and embedded webviews block, which leaves the map a silent black canvas —
// whereas raster PNG tiles load everywhere. CARTO's dark tiles carry
// real street labels, and the paint boost below lifts their contrast so the
// map stays readable in dark mode instead of dissolving into near-black.
const TILE_LIGHT = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const TILE_DARK = "https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png";

// Raster style. `mode` is "light" | "dark" | "dark-fallback":
//  - light: plain OSM tiles.
//  - dark: CARTO dark tiles with a gentle lift (brightness + contrast) so
//    roads and street labels stay legible instead of dissolving into
//    near-black (the original complaint).
//  - dark-fallback: dimmed plain OSM tiles when CARTO's CDN is unreachable,
//    kept dark enough to match the theme but with labels intact.
type RasterMode = "light" | "dark" | "dark-fallback";
const MAP_STYLE = (tiles: string, mode: RasterMode): StyleSpecification => ({
  version: 8,
  // Key-free glyph server so symbol layers (zoom-aware area labels) can
  // render text — the raster basemap carries no glyphs of its own.
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
              // Phase 7 v3: lifted brightness floor + gentler contrast so CARTO's
              // dark tiles keep roads and street labels readable instead of
              // dissolving into near-black (the original dark-mode complaint).
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

/** Escape text before it enters popup HTML (defence-in-depth — backend
 * sanitizes titles, but map popups interpolate area names too). */
function escHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** Debounce map-move refetches so panning doesn't hammer the API. */
function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(t);
  }, [value, delayMs]);
  return debounced;
}

type MapLayerId =
  "universities" | "metro" | "hospital" | "market" | "park" | "mosque" | "bus_terminal";

export default function Map() {
  const darkMode = useUiStore((s) => s.darkMode);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markersRef = useRef<maplibregl.Marker[]>([]);
  // Live rooms for the once-per-map event handlers (see clustering effect).
  const roomsRef = useRef<Room[]>([]);
  // Guards the once-per-map registration of cluster click/hover handlers.
  const clusterHandlersRef = useRef<maplibregl.Map | null>(null);
  // Guards the once-per-map registration of landmark/metro/heatmap/isochrone
  // interaction handlers (Phase 7 v3).
  const interactionHandlersRef = useRef<maplibregl.Map | null>(null);
  const pickDestinationRef = useRef(false);
  // The cluster stats popup — closed before opening another / on map move so
  // a stale "N rooms here" bubble can't linger over changed geometry.
  const clusterPopupRef = useRef<maplibregl.Popup | null>(null);
  const [selectedRoom, setSelectedRoom] = useState<Room | null>(null);
  const [shareCopied, setShareCopied] = useState(false);
  const [showLandmarks, setShowLandmarks] = useState<Record<MapLayerId, boolean>>({
    universities: true,
    metro: true,
    hospital: false,
    market: false,
    park: false,
    mosque: false,
    bus_terminal: false,
  });
  // Area boundaries + zoom-aware labels (on by default; can be toggled off
  // for a cleaner pin view — the filter itself is unaffected).
  const [showAreas, setShowAreas] = useState(true);
  const [heatmap, setHeatmap] = useState(false);
  const [clustering, setClustering] = useState(true);
  const [listOpen, setListOpen] = useState(false);
  const [showTravel, setShowTravel] = useState(false);
  const [activeRoomId, setActiveRoomId] = useState<number | null>(null);
  // Selected area boundary (Phase 7 v3 — boundary click filters the list).
  // `name` is what goes into the URL + the `area=` filter; `key`/`kind`
  // drive the highlight. Clicking empty map space clears it.
  const [selectedArea, setSelectedArea] = useState<{
    key: string;
    name: string;
    kind: AreaKind;
    parentName: string | null;
  } | null>(null);
  // Boundary hover — subtle fill + stronger ring via feature-state. Kept in
  // a ref (not state) so a mousemove across bubbles doesn't re-run the whole
  // boundary effect — feature-state paints update live without a re-render.
  const hoverAreaKeyRef = useRef<string | null>(null);
  // Mirror of `selectedArea` for the map-level empty-click handler (which is
  // registered once per map instance and can't close over fresh state).
  const selectedAreaRef = useRef<{ key: string } | null>(null);
  // Landmark-nearby search (Phase 7 v3): nearest N landmark category within
  // a radius. Feeds ?near_landmark=&radius_km= to the room list API.
  const [nearbyFilter, setNearbyFilter] = useState<{
    kind: LandmarkKind;
    distanceKm: number;
  } | null>(null);
  // The landmark slug resolved for `nearbyFilter` (nearest of its kind to
  // the current map centre — recomputed when the viewport settles).
  const [nearbyLandmarkKey, setNearbyLandmarkKey] = useState<string | null>(null);
  // The filter identity we last flew to for (kind@distance) — so the map
  // centres on the chosen landmark once per apply, not on every pan.
  const flownNearbyForRef = useRef<string | null>(null);

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
  // Live zoom — powers the layer-dependency hints (a category toggle that's
  // only meaningful when zoomed in enough shouldn't look "broken" at low
  // zoom; we say "Zoom in to see…" instead). Kept in state because it's
  // rendered in the toolbar/legend, not just read by map layers.
  const [mapZoom, setMapZoom] = useState(DHAKA_ZOOM);

  // ---- radius search state --------------------------------------------
  // Live mirror of radiusCenter for the once-registered map interaction
  // handlers (their closures are created when the map first becomes ready).
  const radiusCenterRef = useRef<{ lat: number; lng: number; label: string } | null>(null);
  const [radiusCenter, setRadiusCenter] = useState<{
    lat: number;
    lng: number;
    label: string;
  } | null>(null);
  // Intelligent Map (Phase 7 v2): AI search / area intel / commute panel.
  const [intelMode, setIntelMode] = useState<MapIntelMode>(null);
  const [selectedIntelArea, setSelectedIntelArea] = useState<string | null>(null);
  const [pickDestination, setPickDestination] = useState(false);
  // The map-click pick mode for the commute destination. A ref mirrors the
  // state so the once-per-map click handler can read it without re-registering.
  pickDestinationRef.current = pickDestination;
  const [destination, setDestination] = useState<{
    lat: number;
    lng: number;
    label: string;
  } | null>(null);
  const [radiusKm, setRadiusKm] = useState(2);
  const [viewbox, setViewbox] = useState<string | null>(null);

  // Shareable map links: the view state (centre/zoom/radius/label) lives in
  // the URL (?center=lat,lng&zoom=z&r=km&q=label), so a link always opens the
  // exact map view it was copied from. `urlAppliedRef` guards the one-time
  // initial read so a later manual pan doesn't re-apply the old params.
  const [, setSearchParams] = useSearchParams();
  const urlAppliedRef = useRef(false);
  const mapReadyRef = useRef(false);

  // Debounced viewport: fires ~300ms after the user stops panning/zooming.
  const debouncedViewbox = useDebouncedValue(viewbox, 300);
  const debouncedRadiusCenter = useDebouncedValue(radiusCenter, 300);
  // Debounced street-search query — autocomplete fires 250ms after typing stops.
  const debouncedSearchQuery = useDebouncedValue(searchQuery, 250);

  const { data: suggestions = [], isFetching: searching } = useGeocode(debouncedSearchQuery);

  // Keep the URL in sync with the map view so links are shareable. Runs on
  // viewport settles (debounced bbox) and radius changes — `replace: true`
  // means panning across Dhaka doesn't litter the history stack.
  useEffect(() => {
    if (!mapReady || !urlAppliedRef.current) return;
    const map = mapRef.current;
    if (!map) return;
    const c = map.getCenter();
    setSearchParams(
      buildMapViewUrl({
        center: { lat: c.lat, lng: c.lng },
        zoom: map.getZoom(),
        radiusKm: radiusCenter ? radiusKm : null,
        label: radiusCenter?.label ?? null,
        roomId: activeRoomId,
        area: selectedArea?.name ?? null,
        near: nearbyFilter?.kind ?? null,
        distanceKm: nearbyFilter?.distanceKm ?? null,
      }),
      { replace: true }
    );
  }, [
    debouncedViewbox,
    radiusCenter,
    radiusKm,
    activeRoomId,
    mapReady,
    setSearchParams,
    selectedArea,
    nearbyFilter,
  ]);

  const filters = useMemo(() => {
    const f: {
      bbox?: string;
      nearLat?: number;
      nearLng?: number;
      radiusKm?: number;
      area?: string;
      nearLandmark?: string;
    } = {};
    if (debouncedRadiusCenter) {
      f.nearLat = debouncedRadiusCenter.lat;
      f.nearLng = debouncedRadiusCenter.lng;
      f.radiusKm = radiusKm;
    } else if (debouncedViewbox) {
      f.bbox = debouncedViewbox;
    }
    // Boundary click: filter by the selected main area (sub-areas/neighbour-
    // hoods filter through their parent so the backend's `area=` — which only
    // knows Room.Area main districts — keeps working).
    if (selectedArea?.parentName) {
      f.area = selectedArea.parentName;
    } else if (selectedArea) {
      f.area = selectedArea.name;
    }
    // Landmark-nearby search: ?near_landmark=<slug>&radius_km=…
    if (nearbyFilter && nearbyLandmarkKey) {
      f.nearLandmark = nearbyLandmarkKey;
      f.radiusKm = nearbyFilter.distanceKm;
    }
    return f;
  }, [
    debouncedViewbox,
    debouncedRadiusCenter,
    radiusKm,
    selectedArea,
    nearbyFilter,
    nearbyLandmarkKey,
  ]);

  const { data: rooms = [], isLoading } = useRooms(filters);
  const { data: landmarks = [] } = useLandmarks();
  const { data: boundaries } = useAreaBoundaries();
  // Keep the empty-click guard's ref in sync with the state (URL restore
  // sets state directly; this covers every other path).
  useEffect(() => {
    if (selectedArea) selectedAreaRef.current = { key: selectedArea.key };
  }, [selectedArea]);

  // Landmark-nearby search (Phase 7 v3): resolve the chosen category to the
  // NEAREST real landmark of that kind to the current map centre, then pass
  // its slug as `near_landmark` so the backend radius-filters the room list.
  // Re-resolves when the category, distance or viewport centre changes.
  useEffect(() => {
    if (!nearbyFilter) {
      setNearbyLandmarkKey(null);
      flownNearbyForRef.current = null;
      return;
    }
    const map = mapRef.current;
    const centre = map?.getCenter();
    if (!map || !centre) return;
    const kind = nearbyFilter.kind;
    let bestKey: string | null = null;
    let bestKm = Infinity;
    // Primitives (not an object union) so TypeScript's control-flow analysis
    // tracks the closure assignment — an object assigned only inside the
    // forEach would stay narrowed to `null` and make the flyTo branch `never`.
    let bestLat: number | null = null;
    let bestLng: number | null = null;
    landmarks.forEach((lm) => {
      if (lm.kind !== kind) return;
      const km = haversineKm(centre.lat, centre.lng, lm.lat, lm.lng);
      if (km < bestKm) {
        bestKm = km;
        bestKey = lm.key;
        bestLat = lm.lat;
        bestLng = lm.lng;
      }
    });
    setNearbyLandmarkKey(bestKey);
    // Fly to the chosen landmark ONCE per applied filter (identity =
    // kind@distance) so the map visibly responds to the list filter — but
    // panning afterwards never yanks the viewport back.
    const identity = `${kind}@${nearbyFilter.distanceKm}`;
    if (bestLat != null && bestLng != null && flownNearbyForRef.current !== identity) {
      flownNearbyForRef.current = identity;
      mapRef.current?.flyTo({ center: [bestLng, bestLat], zoom: 13 });
    }
  }, [nearbyFilter, landmarks, debouncedViewbox]);
  // Authoritative room counts for the badge (COUNT/AVG server-side — the
  // paginated list caps at one page, so client-side counting undercounts).
  const { data: summary } = useMapSummary(filters);
  // Value scores for the visible viewport (Intelligent Map — transparent
  // price/quality/demand/metro blend, server-computed and cached).
  const { data: valueScores } = useValueScores(rooms.slice(0, 40).map((r) => r.id));
  roomsRef.current = rooms;

  // ---- map bootstrap ---------------------------------------------------
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    // Raster tiles: CARTO dark / OSM light. CARTO's CDN is occasionally
    // unreachable, so `darkTileFallback` re-renders on dimmed OSM tiles.
    const style = darkTileFallback
      ? MAP_STYLE(darkMode ? TILE_LIGHT : TILE_LIGHT, darkMode ? "dark-fallback" : "light")
      : MAP_STYLE(darkMode ? TILE_DARK : TILE_LIGHT, darkMode ? "dark" : "light");
    // Point MapLibre at the bundled worker (see the ?url import above) so
    // symbol layers — zoom-aware area labels, cluster counts — can render.
    // Idempotent: re-applied on every map (re)creation with the same URL.
    maplibregl.setWorkerUrl(maplibreWorkerUrl);
    const map = new maplibregl.Map({
      container: containerRef.current,
      style,
      center: DHAKA_CENTER,
      zoom: DHAKA_ZOOM,
      attributionControl: { compact: true },
    });
    mapRef.current = map;
    // Mark the URL as read as soon as this map owns the container — the
    // load-handler guard below is only about applying shared-link params.
    urlAppliedRef.current = true;
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
      setMapZoom(map.getZoom());
    };

    const applyUrlView = () => {
      // Apply a shared-link view (?center=...,&zoom=...,&r=...,&q=...) once.
      // The map is constructed with the Dhaka default, so if the URL carries
      // a view we jump to it before syncing the viewport.
      const urlView = parseMapViewUrl(window.location.search);
      if (urlView.center) {
        map.jumpTo({ center: [urlView.center[1], urlView.center[0]] });
      }
      if (urlView.zoom != null) {
        map.setZoom(urlView.zoom);
      }
      if (urlView.room != null) {
        setActiveRoomId(urlView.room);
      }
      if (urlView.radiusKm != null && urlView.query) {
        setRadiusKm(urlView.radiusKm);
        setRadiusCenter({
          lat: (urlView.center ?? [DHAKA_CENTER[1], DHAKA_CENTER[0]])[0],
          lng: (urlView.center ?? [DHAKA_CENTER[1], DHAKA_CENTER[0]])[1],
          label: urlView.query,
        });
      }
      if (urlView.area) {
        const area = {
          key: "",
          name: urlView.area,
          kind: "main_area" as AreaKind,
          parentName: null,
        };
        selectedAreaRef.current = area;
        setSelectedArea(area);
      }
      // Landmark-nearby filter from ?near=<kind>&distance=<km>.
      if (urlView.near) {
        const kind = urlView.near as LandmarkKind;
        setNearbyFilter({
          kind,
          distanceKm: urlView.distanceKm ?? 1,
        });
      }
    };
    const finishLoad = () => {
      if (mapReadyRef.current) return; // guard: only once per map instance
      mapReadyRef.current = true;
      urlAppliedRef.current = true;
      setMapReady(true);
      syncViewbox();
    };
    map.on("load", finishLoad);
    // Apply a URL-carried view once the style is up (before the first
    // viewport sync so the badge/bbox match the shared link).
    map.once("styledata", applyUrlView);
    map.once("load", applyUrlView);
    // Safety net: some embedded webviews never fire the map's `load` event
    // (e.g. the tile CDN's .pbf requests are blocked, so `loaded()` never
    // returns true even though the style + sprites rendered). Waiting for
    // `styledata` and then declaring the map ready lets the room layers,
    // URL handling and radius search come up anyway — the GeoJSON layers we
    // add don't need basemap tiles to function.
    map.once("styledata", () => {
      window.setTimeout(finishLoad, 250);
    });
    map.on("moveend", syncViewbox);

    // Clicking empty map space clears the radius search and the active pin —
    // unless the user is picking a commute destination.
    map.on("click", (e: maplibregl.MapMouseEvent) => {
      if (e.originalEvent.target === map.getCanvas()) {
        if (pickDestinationRef.current) {
          setDestination({
            lat: e.lngLat.lat,
            lng: e.lngLat.lng,
            label: "Pinned point",
          });
          setPickDestination(false);
          return;
        }
        setRadiusCenter(null);
        setActiveRoomId(null);
        // Empty click clears the selected boundary — but only when the click
        // didn't land on a boundary bubble itself (layer click handlers fire
        // first and re-select; queryRenderedFeatures tells us the truth).
        const hitBoundary = map
          .queryRenderedFeatures(e.point, {
            layers: [
              "area-boundary-line-main",
              "area-boundary-line-sub",
              "area-boundary-line-nbhd",
            ],
          })
          .some((f) => f.properties?.key);
        if (!hitBoundary) {
          const prevKey = selectedAreaRef.current?.key;
          if (prevKey) {
            map.setFeatureState({ source: "area-boundaries", id: prevKey }, { selected: false });
          }
          selectedAreaRef.current = null;
          setSelectedArea(null);
        }
      }
    });

    map.on("error", (e) => {
      // A single raster tile 404 is benign; only real fetch/network failures
      // matter. When the vector style CDN is unreachable we rebuild the map
      // on raster tiles (dimmed OSM in dark mode) instead of showing a black,
      // unreadable canvas.
      const msg = (e?.error as Error | undefined)?.message ?? "";
      if (/Failed to fetch|NetworkError|timeout|ERR_/i.test(msg)) {
        if (!darkTileFallback) {
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
      mapReadyRef.current = false;
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

    // Category → MapLibre source/layer id. Universities and metro keep
    // their own dot layers (small, always useful); the everyday categories
    // (hospital/market/park/mosque/bus_terminal) share one CLUSTERED source
    // so nearby places group into a count bubble at low zoom and split into
    // per-kind dots as you zoom in (zoom-based visibility via per-kind
    // minzoom on the dot layers — see landmarkMinzoom).
    const DOT_LAYER: Record<LandmarkKind, string> = {
      university: "universities",
      metro: "metro",
      hospital: "places-hospital",
      market: "places-market",
      park: "places-park",
      mosque: "places-mosque",
      bus_terminal: "places-bus-terminal",
    };

    // Universities + metro: simple dot layers (kept from Phase 7).
    (["university", "metro"] as const).forEach((kind) => {
      const group = landmarks.filter((l) => l.kind === kind);
      const meta = LANDMARK_KIND_META[kind];
      addSourceLayer(DOT_LAYER[kind], landmarksToFeatureCollection(group), {
        "circle-radius": kind === "university" ? 6 : 5,
        "circle-color": meta.color,
        "circle-stroke-color": "#ffffff",
        "circle-stroke-width": 1.5,
        "circle-opacity": 0.9,
      });
    });

    // Everyday categories: one clustered source + per-kind dot layers.
    const PLACES_SOURCE = "places-clusters";
    const places = landmarks.filter((l) => l.kind !== "university" && l.kind !== "metro");
    try {
      if (!map.getSource(PLACES_SOURCE)) {
        map.addSource(PLACES_SOURCE, {
          type: "geojson",
          data: landmarksToFeatureCollection(places),
          cluster: true,
          clusterMaxZoom: 13,
          clusterRadius: 44,
        });
        map.addLayer(
          {
            id: "places-clusters-layer",
            type: "circle",
            source: PLACES_SOURCE,
            filter: ["has", "point_count"],
            paint: {
              "circle-color": [
                "step",
                ["get", "point_count"],
                "#0d9488",
                6,
                "#0f766e",
                12,
                "#115e59",
              ],
              "circle-radius": ["step", ["get", "point_count"], 18, 6, 24, 12, 30],
              "circle-opacity": 0.85,
              "circle-stroke-color": "#ffffff",
              "circle-stroke-width": 1.5,
            },
          },
          // Above the area boundaries, below the room markers.
          map.getLayer("rooms-clusters-layer") ? "rooms-clusters-layer" : undefined
        );
        map.addLayer(
          {
            id: "places-clusters-count",
            type: "symbol",
            source: PLACES_SOURCE,
            filter: ["has", "point_count"],
            layout: {
              "text-field": ["get", "point_count_abbreviated"],
              "text-size": 12,
              "text-font": ["DIN Offc Pro Medium", "Arial Unicode MS Bold"],
            },
            paint: { "text-color": "#ffffff" },
          },
          map.getLayer("rooms-clusters-layer") ? "rooms-clusters-layer" : undefined
        );
      } else {
        (map.getSource(PLACES_SOURCE) as maplibregl.GeoJSONSource).setData(
          landmarksToFeatureCollection(places)
        );
      }
      // Per-kind unclustered dots — zoom-based visibility via minzoom.
      (["hospital", "market", "park", "mosque", "bus_terminal"] as const).forEach((kind) => {
        const id = DOT_LAYER[kind];
        const meta = LANDMARK_KIND_META[kind];
        if (map.getLayer(id)) {
          map.getSource(PLACES_SOURCE) as maplibregl.GeoJSONSource;
          return;
        }
        map.addLayer(
          {
            id,
            type: "circle",
            source: PLACES_SOURCE,
            filter: ["all", ["!", ["has", "point_count"]], ["==", ["get", "kind"], kind]],
            minzoom: landmarkMinzoom(kind),
            paint: {
              "circle-radius": 5,
              "circle-color": meta.color,
              "circle-stroke-color": "#ffffff",
              "circle-stroke-width": 1.5,
              "circle-opacity": 0.9,
            },
          },
          map.getLayer("rooms-clusters-layer") ? "rooms-clusters-layer" : undefined
        );
      });
    } catch {
      // Layer juggling during rapid toggles — safe to ignore.
    }
  }, [landmarks, mapReady]);

  // ---- area boundary polygons + labels (Phase 7 v3) ----------------------
  // Approximate boundary bubbles from /rooms/area-boundaries/ — main areas
  // strong, sub-areas medium, neighbourhoods subtle — with zoom-based
  // visibility so the map never drowns in rings: main areas appear from
  // z≈10, sub-areas from z≈12, neighbourhoods from z≈13.5. Clicking a bubble
  // FILTERS the room list to that area (Phase 7 v3 — connected interaction:
  // boundary → area filter → list + URL + highlight); hovering subtly lifts
  // the bubble via feature-state. Zoom-aware text labels sit on top, each
  // kind appearing at its own zoom (AREA_LABEL_MINZOOM).
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    if (!boundaries) return;
    const SOURCE = "area-boundaries";
    const LABEL_SOURCE = "area-labels";
    const LINE_IDS = [
      "area-boundary-line-main",
      "area-boundary-line-sub",
      "area-boundary-line-nbhd",
    ] as const;
    // Read the CURRENT theme at creation so a map built in dark mode gets
    // dark-tuned labels/boundaries immediately (the theme-swap effect only
    // re-paints layers that already exist, so creation-time theme matters).
    const dark = useUiStore.getState().darkMode;
    try {
      if (!map.getSource(SOURCE)) {
        // promoteId: "key" lets feature-state address each bubble by its
        // stable area slug (hover/selected highlight without new layers).
        map.addSource(SOURCE, {
          type: "geojson",
          data: boundaries as GeoJSON.FeatureCollection,
          promoteId: "key",
        });
        const spec: {
          id: string;
          kind: "main_area" | "sub_area" | "neighborhood";
          type: "fill" | "line";
          minzoom: number;
          paint: Record<string, unknown>;
        }[] = [
          {
            id: "area-boundary-fill-main",
            kind: "main_area",
            type: "fill",
            minzoom: 9.5,
            paint: {
              "fill-color": "#f97316",
              // Selected > hover > default — feature-state keeps the highlight
              // live without rebuilding layers; the expression builder bakes
              // the theme in so dark mode keeps the states too.
              "fill-opacity": areaBoundaryFillOpacity("main_area", dark),
            },
          },
          {
            id: "area-boundary-line-main",
            kind: "main_area",
            type: "line",
            minzoom: 9.5,
            paint: {
              "line-color": areaBoundaryLineColor("main_area", dark),
              "line-width": [
                "case",
                ["==", ["feature-state", "selected"], true],
                4,
                ["==", ["feature-state", "hover"], true],
                3,
                2.5,
              ],
              "line-opacity": 0.75,
            },
          },
          {
            id: "area-boundary-fill-sub",
            kind: "sub_area",
            type: "fill",
            minzoom: 11.5,
            paint: {
              "fill-color": "#3b82f6",
              "fill-opacity": areaBoundaryFillOpacity("sub_area", dark),
            },
          },
          {
            id: "area-boundary-line-sub",
            kind: "sub_area",
            type: "line",
            minzoom: 11.5,
            paint: {
              "line-color": areaBoundaryLineColor("sub_area", dark),
              "line-width": [
                "case",
                ["==", ["feature-state", "selected"], true],
                3,
                ["==", ["feature-state", "hover"], true],
                2,
                1.5,
              ],
              "line-opacity": 0.6,
            },
          },
          {
            id: "area-boundary-fill-nbhd",
            kind: "neighborhood",
            type: "fill",
            minzoom: 13.5,
            paint: {
              "fill-color": "#7c3aed",
              "fill-opacity": areaBoundaryFillOpacity("neighborhood", dark),
            },
          },
          {
            id: "area-boundary-line-nbhd",
            kind: "neighborhood",
            type: "line",
            minzoom: 13.5,
            paint: {
              "line-color": areaBoundaryLineColor("neighborhood", dark),
              "line-width": [
                "case",
                ["==", ["feature-state", "selected"], true],
                2.5,
                ["==", ["feature-state", "hover"], true],
                1.5,
                1,
              ],
              "line-opacity": 0.5,
            },
          },
        ];
        spec.forEach(({ id, kind, type, minzoom, paint }) => {
          // Spread `type` first so TS narrows the union per iteration.
          map.addLayer(
            {
              ...{ type },
              id,
              source: SOURCE,
              filter: ["==", ["get", "kind"], kind],
              minzoom,
              paint,
            } as maplibregl.LayerSpecification,
            // Below the room markers so pins stay clickable on top.
            map.getLayer("rooms-clusters-layer") ? "rooms-clusters-layer" : undefined
          );
        });
      }

      // ---- zoom-aware area labels --------------------------------------
      // Point labels at each area's real centre, one symbol layer per
      // hierarchy kind with its own minzoom (main areas first, then sub-
      // areas, then neighbourhoods). Colors/halos swap with the theme via
      // THEME_PAINTS so text stays readable on dark tiles.
      if (!map.getSource(LABEL_SOURCE)) {
        map.addSource(LABEL_SOURCE, {
          type: "geojson",
          data: boundaryLabelsToFeatureCollection(
            boundaries as unknown as {
              type: "FeatureCollection";
              features: { properties?: Record<string, unknown> | null }[];
            }
          ),
        });
        (
          [
            ["area-label-main", "main_area"],
            ["area-label-sub", "sub_area"],
            ["area-label-nbhd", "neighborhood"],
          ] as const
        ).forEach(([id, kind]) => {
          map.addLayer(
            {
              id,
              type: "symbol",
              source: LABEL_SOURCE,
              filter: ["==", ["get", "kind"], kind],
              minzoom: AREA_LABEL_MINZOOM[kind] ?? 12,
              layout: {
                "text-field": ["get", "name"],
                "text-size": kind === "main_area" ? 13 : 11,
                // "Noto Sans Regular" is served by the key-free glyph server;
                // a font NOT on that server (e.g. "Arial Unicode MS Regular")
                // would 404 the glyph request and blank the whole label.
                "text-font": ["Noto Sans Regular"],
                "text-anchor": "center",
                "text-letter-spacing": 0.02,
              },
              // Theme-aware paint baked in at creation (light: dark text +
              // white halo; dark: near-white text + dark halo). The
              // theme-swap effect also re-applies these via THEME_PAINTS so
              // toggling after load keeps the labels readable. themePaintValue
              // returns `unknown`, so the fallback cast pins the type.
              paint: {
                "text-color": (themePaintValue(id, "text-color", dark) ??
                  (kind === "main_area" ? "#1f2937" : "#4b5563")) as string,
                "text-halo-color": (themePaintValue(id, "text-halo-color", dark) ??
                  "#ffffff") as string,
                "text-halo-width": kind === "main_area" ? 2 : 1.5,
                "text-halo-blur": 0.5,
              },
            },
            map.getLayer("rooms-clusters-layer") ? "rooms-clusters-layer" : undefined
          );
        });
      }

      // ---- boundary interactions (click filters, hover lifts) -----------
      const pointer = (on: boolean) => () => {
        map.getCanvas().style.cursor = on ? "pointer" : "";
      };
      const setState = (key: string, state: Record<string, boolean>) => {
        try {
          map.setFeatureState({ source: SOURCE, id: key }, state);
        } catch {
          // Feature id not present (source data changed) — no-op.
        }
      };

      // A URL-restored selection (?area=…) has no key (the slug isn't in the
      // URL) — resolve it from the boundary data so the highlight lands.
      if (selectedArea && !selectedArea.key) {
        const features = (
          boundaries as unknown as {
            type: "FeatureCollection";
            features: { properties?: Record<string, unknown> | null }[];
          }
        ).features;
        const match = features.find(
          (f) =>
            typeof f.properties?.name === "string" &&
            f.properties.name.toLowerCase() === selectedArea.name.toLowerCase()
        );
        const resolvedKey = match?.properties?.key ? String(match.properties.key) : null;
        if (resolvedKey) {
          selectedAreaRef.current = { key: resolvedKey };
          setSelectedArea({ ...selectedArea, key: resolvedKey });
          setState(resolvedKey, { selected: true });
        }
      }

      // All handlers are removed before being re-added so the effect's
      // re-runs (rooms/selectedArea change on every refetch + click) never
      // stack duplicate listeners — a stacked click handler would open the
      // same popup N times.
      const onClick = (e: maplibregl.MapLayerMouseEvent) => {
        const f = e.features?.[0];
        if (!f) return;
        const p = (f.properties ?? {}) as Record<string, string>;
        const key = String(p.key ?? "");
        const name = String(p.name ?? "");
        const kind = (p.kind ?? "main_area") as AreaKind;
        const parentName = (p.parent_name as string | null) ?? null;
        // Select + highlight this boundary, clear the previous selection.
        if (selectedArea?.key && selectedArea.key !== key) {
          setState(selectedArea.key, { selected: false });
        }
        setSelectedArea({ key, name, kind, parentName });
        selectedAreaRef.current = { key };
        setState(key, { selected: true, hover: false });
        // Fly to the area's real centre so the filter is VISIBLE — clicking
        // a boundary must answer with pins + list results, not an empty
        // "No rooms in view" because the selected area sits off-viewport.
        // Zoom matches the hierarchy level: main areas land at a street-
        // readable zoom, sub-areas closer, neighbourhoods closer still.
        const centreLat = Number(p.lat);
        const centreLng = Number(p.lng);
        if (Number.isFinite(centreLat) && Number.isFinite(centreLng)) {
          const zoomForKind = kind === "neighborhood" ? 14.5 : kind === "sub_area" ? 13.5 : 12;
          map.flyTo({ center: [centreLng, centreLat], zoom: zoomForKind });
        }
        // The area's real listing stats + the filter applied.
        const stats = areaStats(roomsRef.current, name);
        new maplibregl.Popup({ closeButton: false, closeOnClick: true, maxWidth: "240px" })
          .setLngLat(e.lngLat)
          .setHTML(
            heatmapPopupHtml(name, stats) +
              `<div class="map-popup__meta" style="margin-top:4px">Filtered to ${escHtml(name)}${
                parentName ? ` (${escHtml(parentName)})` : ""
              }</div>`
          )
          .addTo(map);
      };
      const pointerIn = pointer(true);
      const pointerOut = pointer(false);
      LINE_IDS.forEach((id) => {
        map.off("click", id, onClick);
        map.off("mouseenter", id, pointerIn);
        map.off("mouseleave", id, pointerOut);
        map.on("click", id, onClick);
        map.on("mouseenter", id, pointerIn);
        map.on("mouseleave", id, pointerOut);
      });

      // Hover: lift the bubble under the cursor (fast + subtle), clear when
      // the pointer leaves a boundary or selects another area. Registered on
      // the three line layers — `mousemove` with a layer id fires only over
      // that layer's rendered features. The listeners are removed first so
      // re-runs (data refresh) never stack them.
      const onHover = (e: maplibregl.MapLayerMouseEvent) => {
        const f = e.features?.[0];
        const key = f ? String((f.properties ?? {}).key ?? "") : null;
        const prev = hoverAreaKeyRef.current;
        if (prev && prev !== key) setState(prev, { hover: false });
        if (key && key !== prev && key !== selectedArea?.key) {
          setState(key, { hover: true });
        }
        hoverAreaKeyRef.current = key;
      };
      const clearHover = () => {
        const prev = hoverAreaKeyRef.current;
        if (prev) setState(prev, { hover: false });
        hoverAreaKeyRef.current = null;
      };
      LINE_IDS.forEach((layerId) => {
        map.off("mousemove", layerId, onHover);
        map.off("mouseleave", layerId, clearHover);
        map.on("mousemove", layerId, onHover);
        map.on("mouseleave", layerId, clearHover);
      });
    } catch {
      // Rapid toggle during layer juggling — safe to ignore.
    }
  }, [boundaries, mapReady, rooms, selectedArea]);

  // Layer visibility follows the toggles — the fixed dot layers keep their
  // own visibility; the shared places cluster (count bubble + per-kind dots)
  // shows when ANY of the everyday categories is on.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    (["universities", "metro"] as MapLayerId[]).forEach((id) => {
      if (map.getLayer(id))
        map.setLayoutProperty(id, "visibility", showLandmarks[id] ? "visible" : "none");
    });
    const placesOn = (["hospital", "market", "park", "mosque", "bus_terminal"] as const).some(
      (k) => showLandmarks[k]
    );
    const placesLayers = [
      "places-clusters-layer",
      "places-clusters-count",
      "places-hospital",
      "places-market",
      "places-park",
      "places-mosque",
      "places-bus-terminal",
    ];
    placesLayers.forEach((id) => {
      if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", placesOn ? "visible" : "none");
    });
    // Area boundaries + zoom-aware labels follow the Areas toggle. Hiding a
    // selected boundary is fine — the `area=` filter and list stay intact.
    const areaLayers = [
      "area-boundary-fill-main",
      "area-boundary-line-main",
      "area-boundary-fill-sub",
      "area-boundary-line-sub",
      "area-boundary-fill-nbhd",
      "area-boundary-line-nbhd",
      "area-label-main",
      "area-label-sub",
      "area-label-nbhd",
    ];
    areaLayers.forEach((id) => {
      if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", showAreas ? "visible" : "none");
    });
  }, [showLandmarks, showAreas, mapReady]);

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

      // Insert the cluster layers BELOW the landmark layers so toggling
      // Universities/Metro always shows their dots on top of the big orange
      // cluster circles (layer order = insertion order in MapLibre).
      const beforeId = map.getLayer("universities") ? "universities" : undefined;

      try {
        if (!map.getSource(CLUSTER_SOURCE)) {
          map.addSource(CLUSTER_SOURCE, {
            type: "geojson",
            data: roomsToFeatureCollection(rooms),
            cluster: true,
            clusterMaxZoom: 14,
            clusterRadius: 50,
            // Roll the member rooms' prices up into each cluster so the label
            // can show the average rent AND the count — one cheap expression,
            // no extra /rooms/summary/ call per cluster.
            clusterProperties: {
              price_sum: ["+", ["get", "price"]],
              price_min: ["min", ["get", "price"]],
              price_max: ["max", ["get", "price"]],
            },
          });
          map.addLayer(
            {
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
                "circle-radius": ["step", ["get", "point_count"], 24, 10, 32, 50, 40],
                "circle-opacity": 0.9,
                "circle-stroke-color": "#ffffff",
                "circle-stroke-width": 2,
              },
            },
            beforeId
          );
          map.addLayer(
            {
              id: CLUSTER_COUNT,
              type: "symbol",
              source: CLUSTER_SOURCE,
              filter: ["has", "point_count"],
              layout: {
                // Count on the first line, average rent on the second —
                // "12 rooms · avg ৳10k" at a glance. Colors chosen to stay
                // readable on both light and dark basemaps.
                "text-field": [
                  "format",
                  ["get", "point_count_abbreviated"],
                  { "font-scale": 1.1 },
                  "\n",
                  {},
                  [
                    "concat",
                    "৳",
                    ["to-string", ["round", ["/", ["get", "price_sum"], ["get", "point_count"]]]],
                  ],
                  { "font-scale": 0.8 },
                ],
                "text-size": 12,
                "text-font": ["DIN Offc Pro Medium", "Arial Unicode MS Bold"],
                "text-line-height": 1.25,
              },
              paint: { "text-color": "#ffffff" },
            },
            beforeId
          );
          map.addLayer(
            {
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
            },
            beforeId
          );
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
          clusterHandlersRef.current = map; // Cluster click -> show a quick count/price summary popup, then
          // zoom in on the cluster (the popup follows the zoom). A stale
          // popup is closed before a new one opens and on any map movement.
          map.on("click", CLUSTER_LAYER, (e) => {
            const feature = e.features?.[0];
            if (!feature) return;
            const props = feature.properties ?? {};
            const count = props.point_count as number;
            const avg = Math.round((props.price_sum as number) / count);
            const min = props.price_min as number;
            const max = props.price_max as number;
            const coords = (feature.geometry as GeoJSON.Point).coordinates as [number, number];
            clusterPopupRef.current?.remove();
            clusterPopupRef.current = new maplibregl.Popup({
              closeButton: false,
              closeOnClick: true,
              maxWidth: "220px",
            })
              .setLngLat(coords)
              .setHTML(
                `
                <div class="map-popup">
                  <div class="map-popup__name">${count} room${count === 1 ? "" : "s"} here</div>
                  <div class="map-popup__meta">avg ৳${avg.toLocaleString()} · ৳${min.toLocaleString()}–৳${max.toLocaleString()}</div>
                  <div class="map-popup__cta">Click to zoom in →</div>
                </div>
              `
              )
              .addTo(map);
            const clusterId = props.cluster_id as number;
            (map.getSource(CLUSTER_SOURCE) as maplibregl.GeoJSONSource)
              .getClusterExpansionZoom(clusterId)
              .then((zoom) => {
                map.easeTo({ center: coords, zoom: zoom + 1 });
              });
          });

          // Don't leave the stats bubble floating over a moved/zoomed map.
          map.on("moveend", () => clusterPopupRef.current?.remove());

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

      // Distance + ETA (walking AND driving) when the query has a reference
      // point, plus a deep-link that opens Google Maps with the route
      // pre-filled (origin = the radius-search point when one is active).
      const distanceLine =
        room.distanceKm != null
          ? `<div class="map-popup__dist">📍 ${formatDistance(room.distanceKm)} away · ${formatTravelTime(room.distanceKm)} · ${formatDriveTime(room.distanceKm)}</div>`
          : "";
      // Nearest MRT station with walking ETA — the "which line do I ride?"
      // answer, straight from the backend's proximity annotation.
      const metroLine = room.proximity?.nearestMetro
        ? `<div class="map-popup__metro">🚇 ${esc(room.proximity.nearestMetro.name)} · ${formatDistance(
            room.proximity.nearestMetro.distanceKm
          )} · ${formatTravelTime(room.proximity.nearestMetro.distanceKm)}</div>`
        : "";
      // Travel-mode picker: each mode is its own Google Maps deep-link, so a
      // tap opens the right route without any popup-state juggling.
      const dirButton = (mode: TravelMode, label: string) =>
        `<a class="map-popup__dir" href="${directionsUrl(
          { lat: room.lat, lng: room.lng },
          radiusCenter,
          mode
        )}" target="_blank" rel="noopener noreferrer">${label}</a>`;
      const directionsRow = `<div class="map-popup__dirs">
          ${dirButton("walking", "🚶 Walk")}
          ${dirButton("driving", "🚗 Drive")}
          ${dirButton("transit", "🚇 Transit")}
        </div>`;
      const valueLine = valueScores?.[room.id]
        ? `<div class="map-popup__value">⭐ Value score <b>${valueScores[room.id].score}/100</b> · ${valueScores[room.id].factors.metro}/100 transit</div>`
        : "";
      // Nearby useful places (nearest of each category within ~3 km, real
      // landmarks only) — click a chip to fly to the place + radius search.
      const nearbyChips = nearbyLandmarkChipsHtml(
        landmarks as { key: string; name: string; kind: LandmarkKind; lat: number; lng: number }[],
        room.lat,
        room.lng
      );
      const popup = new maplibregl.Popup({ offset: 22, closeButton: false, maxWidth: "290px" })
        .setHTML(`
        <div class="map-popup">
          <div class="map-popup__price">৳${room.price.toLocaleString()}<span>/mo</span></div>
          <div class="map-popup__name">${esc(room.name)}</div>
          <div class="map-popup__meta">${esc(room.area)} · ${esc(room.type)} · ★ ${room.rating} (${room.reviews})</div>
          ${valueLine}
          ${nearbyChips}
          ${metroLine}
          ${distanceLine}
          ${directionsRow}
          <div class="map-popup__cta">View listing →</div>
        </div>
      `);
      // Chip click → fly to the landmark + start a radius search around it
      // (reuses the same interaction as university/metro dot clicks).
      popup.on("open", () => {
        popup
          .getElement()
          .querySelectorAll("[data-chip-key]")
          .forEach((chip) => {
            const key = (chip as HTMLElement).dataset.chipKey;
            const lm = landmarks.find((l) => l.key === key);
            if (!lm) return;
            chip.addEventListener("click", () => {
              setRadiusCenter({ lat: lm.lat, lng: lm.lng, label: lm.name });
              setRadiusKm(2);
              mapRef.current?.flyTo({
                center: [lm.lng, lm.lat],
                zoom: Math.max(mapRef.current.getZoom(), 13.5),
              });
            });
          });
      });

      const marker = new maplibregl.Marker({ element: el, anchor: "bottom" })
        .setLngLat([room.lng, room.lat])
        .setPopup(popup)
        .addTo(map);

      el.addEventListener("click", () => openRoom(room));
      markersRef.current.push(marker);
    });
    // radiusCenter feeds the popup's directions origin, so markers rebuild
    // when the search point moves (they also refetch rooms then anyway).
  }, [rooms, mapReady, clustering, radiusCenter, valueScores, landmarks]);

  // Destination pin for the commute mode — a teal flag the user drops by
  // clicking the map (or via the panel), persisted in URL state.
  useEffect(() => {
    if (!mapReady || !destination) return;
    const el = document.createElement("div");
    el.className = "map-destination-pin";
    el.setAttribute("aria-label", "Commute destination");
    el.innerHTML = "🎯";
    const marker = new maplibregl.Marker({ element: el, anchor: "bottom" })
      .setLngLat([destination.lng, destination.lat])
      .addTo(mapRef.current!);
    return () => {
      marker.remove();
    };
  }, [mapReady, destination]);

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

  useEffect(() => {
    radiusCenterRef.current = radiusCenter;
  }, [radiusCenter]);

  // Deep-link: a shared ?room=123 URL selects that listing once its row is
  // in the loaded set, reopening the same popup/modal the click would.
  useEffect(() => {
    if (activeRoomId == null) return;
    const room = rooms.find((r) => r.id === activeRoomId);
    if (room && !selectedRoom) {
      setSelectedRoom(room);
    }
  }, [activeRoomId, rooms, selectedRoom]);

  // ---- interaction layer (Phase 7 v3) ------------------------------------
  // Click/hover wiring for the layers that previously "did nothing":
  // university dots, metro station dots, the MRT Line-6 corridor, the price
  // heatmap and the walking isochrone bands. Registered ONCE per map instance
  // (MapLibre .on() does not dedupe); every number comes from the ACTUAL
  // rooms in view (roomsRef) via the pure helpers in lib/mapInteractions.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    if (interactionHandlersRef.current === map) return;
    interactionHandlersRef.current = map;
    // Non-null alias for closures — TS drops the narrowing inside nested
    // function declarations.
    const m = map;

    // Per-kind CTA label: universities/metro already had one; the everyday
    // categories (hospital/market/…) reuse the same "find rooms near" action.
    const kindCta = (kind: LandmarkKind) =>
      kind === "university"
        ? "Find rooms near this university →"
        : kind === "metro"
          ? "Rooms near this station →"
          : "Rooms near here →";

    const openLandmarkPopup = (
      kind: LandmarkKind,
      name: string,
      lat: number,
      lng: number,
      e: maplibregl.MapMouseEvent
    ) => {
      const stats = nearbyStats(roomsRef.current, lat, lng, 2); // ~2 km radius
      const popup = new maplibregl.Popup({
        closeButton: false,
        closeOnClick: true,
        maxWidth: "260px",
      })
        .setLngLat(e.lngLat)
        .setHTML(landmarkPopupHtml(kind, name, stats, kindCta(kind)))
        .addTo(m);
      // CTA -> start a radius search around the landmark (real rooms only).
      const cta = popup.getElement().querySelector('[data-map-cta="nearby"]');
      cta?.addEventListener("click", () => {
        setRadiusCenter({ lat, lng, label: name });
        setRadiusKm(2);
        m.flyTo({ center: [lng, lat], zoom: Math.max(m.getZoom(), 13.5) });
      });
    };

    const pointer = (on: boolean) => () => {
      m.getCanvas().style.cursor = on ? "pointer" : "";
    };

    // Landmark coordinates come from the feature GEOMETRY (the layer's
    // features only carry name/kind in their properties).
    const landmarkCoords = (f: GeoJSON.Feature): [number, number] => {
      const c = (f.geometry as GeoJSON.Point).coordinates;
      return [Number(c[1]), Number(c[0])]; // [lat, lng]
    };

    // Universities (purple dots).
    map.on("click", "universities", (e) => {
      const f = e.features?.[0];
      if (!f) return;
      const p = (f.properties ?? {}) as Record<string, string>;
      const [lat, lng] = landmarkCoords(f);
      openLandmarkPopup("university", p.name || "University", lat, lng, e);
    });
    map.on("mouseenter", "universities", pointer(true));
    map.on("mouseleave", "universities", pointer(false));

    // Metro stations (teal dots).
    map.on("click", "metro", (e) => {
      const f = e.features?.[0];
      if (!f) return;
      const p = (f.properties ?? {}) as Record<string, string>;
      const [lat, lng] = landmarkCoords(f);
      openLandmarkPopup("metro", p.name || "Metro station", lat, lng, e);
    });
    map.on("mouseenter", "metro", pointer(true));
    map.on("mouseleave", "metro", pointer(false));

    // Everyday categories (hospital/market/park/mosque/bus_terminal) —
    // dot layers over the shared clustered source. Clicking a dot opens the
    // same real-data popup; clicking a count bubble zooms into the cluster.
    const PLACE_DOT_LAYERS = [
      "places-hospital",
      "places-market",
      "places-park",
      "places-mosque",
      "places-bus-terminal",
    ] as const;
    PLACE_DOT_LAYERS.forEach((layerId) => {
      map.on("click", layerId, (e) => {
        const f = e.features?.[0];
        if (!f) return;
        const p = (f.properties ?? {}) as Record<string, string>;
        const kind = (p.kind ?? layerId.replace("places-", "")) as LandmarkKind;
        const meta = LANDMARK_KIND_META[kind];
        const [lat, lng] = landmarkCoords(f);
        openLandmarkPopup(kind, p.name || meta.label, lat, lng, e);
      });
      map.on("mouseenter", layerId, pointer(true));
      map.on("mouseleave", layerId, pointer(false));
    });

    // Count bubble on the shared places source → zoom into the cluster
    // (same expansion behaviour as the room clusters).
    map.on("click", "places-clusters-layer", (e) => {
      const f = e.features?.[0];
      if (!f) return;
      const source = map.getSource("places-clusters") as maplibregl.GeoJSONSource;
      const clusterId = f.properties?.cluster_id as number;
      if (!source || clusterId == null) return;
      source
        .getClusterExpansionZoom(clusterId)
        .then((zoom) => m.easeTo({ center: e.lngLat, zoom: zoom + 1 }));
    });
    map.on("mouseenter", "places-clusters-layer", pointer(true));
    map.on("mouseleave", "places-clusters-layer", pointer(false));

    // MRT Line-6 corridor line.
    map.on("click", "metro-route", (e) => {
      new maplibregl.Popup({ closeButton: false, closeOnClick: true, maxWidth: "240px" })
        .setLngLat(e.lngLat)
        .setHTML(metroRoutePopupHtml())
        .addTo(m);
    });
    map.on("mouseenter", "metro-route", pointer(true));
    map.on("mouseleave", "metro-route", pointer(false));

    // Price heatmap — click shows the clicked listing's area stats.
    map.on("click", "price-heatmap", (e) => {
      const f = e.features?.[0];
      if (!f) return;
      const area = String((f.properties ?? {}).area ?? "");
      const stats = areaStats(roomsRef.current, area);
      new maplibregl.Popup({ closeButton: false, closeOnClick: true, maxWidth: "240px" })
        .setLngLat(e.lngLat)
        .setHTML(heatmapPopupHtml(area, stats))
        .addTo(m);
    });
    map.on("mouseenter", "price-heatmap", pointer(true));
    map.on("mouseleave", "price-heatmap", pointer(false));

    // Walking isochrone bands — click shows how many rooms are inside.
    const BAND_MINUTES = [10, 20, 30];
    map.on("click", "travel-bands-0", (e) => showBandStats(0, e));
    map.on("click", "travel-bands-1", (e) => showBandStats(1, e));
    map.on("click", "travel-bands-2", (e) => showBandStats(2, e));
    function showBandStats(band: number, e: maplibregl.MapMouseEvent) {
      const center = radiusCenterRef.current;
      if (!center) return;
      const minutes = BAND_MINUTES[band];
      const radiusKm = (minutes / 60) * 4.5; // WALKING_SPEED_KMH
      const stats = isochroneStats(roomsRef.current, center, radiusKm);
      new maplibregl.Popup({ closeButton: false, closeOnClick: true, maxWidth: "240px" })
        .setLngLat(e.lngLat)
        .setHTML(isochronePopupHtml(minutes, stats))
        .addTo(m);
    }
    ["travel-bands-0", "travel-bands-1", "travel-bands-2"].forEach((id) => {
      m.on("mouseenter", id, pointer(true));
      m.on("mouseleave", id, pointer(false));
    });
  }, [mapReady]);

  // ---- dark-theme paint swap (Phase 7 v3) --------------------------------
  // The basemap style swaps on theme change, but the overlay layers (pins,
  // clusters, heatmap, isochrone bands, metro/landmark dots) are added with
  // light-tuned paints. This effect re-paints them via setPaintProperty when
  // darkMode flips so they stay readable on the dark CARTO basemap — without
  // rebuilding the layers (which would lose map state). Layers that aren't
  // currently shown are skipped; the effect re-runs on mapReady and on every
  // layer toggle so layers turned on after the theme swap still get the
  // correct paint on their first render.
  //
  // The actual dark/light values live in lib/mapInteractions (THEME_PAINTS) —
  // pure data, unit-tested — so this effect is just "apply the map".
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const dark = darkMode;

    // Layers differ in type (circle/line/fill/symbol), so the property name
    // can't be a single keyof AllPaintProperties — a runtime-guarded cast is
    // the pragmatic call (the try/catch swallows genuinely invalid combos).
    const set = (
      layer: string,
      prop: Parameters<typeof map.setPaintProperty>[1],
      value: unknown
    ) => {
      if (map.getLayer(layer)) {
        try {
          map.setPaintProperty(layer, prop, value as never);
        } catch {
          // Layer exists but the property isn't paintable in this context.
        }
      }
    };

    Object.entries(THEME_PAINTS).forEach(([layer, patches]) => {
      patches.forEach(({ prop, dark: darkVal, light }) => {
        set(layer, prop as Parameters<typeof map.setPaintProperty>[1], dark ? darkVal : light);
      });
    });

    // Walking isochrone bands — stronger fill + outline on dark (the 0.1
    // opacity light-mode tint is invisible over dark tiles). The per-band
    // colors stay the same in both themes; only opacity + outline change.
    [0, 1, 2].forEach((i) => {
      const id = `travel-bands-${i}`;
      set(id, "fill-opacity", dark ? TRAVEL_BAND_DARK_OPACITY : TRAVEL_BAND_LIGHT_OPACITY);
      if (dark) set(id, "fill-outline-color", "#ffffff");
    });
  }, [darkMode, mapReady, showLandmarks, heatmap, clustering, showTravel, radiusCenter]);

  // Room-count badge: prefer the authoritative server summary (COUNT/AVG over
  // every row in view, not just page 1); fall back to the client-side list
  // while the summary request is in flight or when it isn't available.
  const counts = useMemo(() => {
    const total = summary?.total ?? rooms.length;
    const available = summary?.available ?? rooms.filter((r) => r.available).length;
    const avg = summary?.avg_price ?? avgPrice(rooms);
    return { total, available, avg: avg != null ? Math.round(avg) : null };
  }, [rooms, summary]);

  // Badge copy that matches the current query mode: during a radius search
  // "1 of 1 rooms in view" is meaningless (the viewport never changed), so
  // say how many rooms are within the chosen radius instead.
  const badgeLabel = useMemo(() => {
    if (radiusCenter) {
      const n = counts.available;
      return `${n} room${n === 1 ? "" : "s"} within ${radiusKm} km of ${radiusCenter.label}`;
    }
    const n = counts.available;
    if (counts.total === n) return `${n} room${n === 1 ? "" : "s"} in view`;
    return `${n} of ${counts.total} rooms in view`;
  }, [radiusCenter, radiusKm, counts]);

  // Areas in the current viewport with their room counts — the map's quick
  // "where are the rooms?" chips. Derived from the same /rooms/summary/ call
  // that powers the badge, so no extra request.
  const areaChips = useMemo(
    () =>
      (summary?.by_area ?? [])
        .filter((a) => a.count > 0 && a.lat != null && a.lng != null)
        .slice(0, 6),
    [summary]
  );

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

        {/* Toolbar */}
        <div className="absolute left-4 top-4 z-10 flex max-w-[calc(100%-2rem)] flex-col gap-3">
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
              onClick={() => setShowLandmarks((s) => ({ ...s, universities: !s.universities }))}
            >
              <LandmarkIcon className="size-4" /> Universities
            </Button>
            <Button
              variant="ghost"
              size="sm"
              aria-pressed={showLandmarks.metro}
              className={cn(
                "gap-1.5 rounded-lg",
                showLandmarks.metro &&
                  "bg-teal-50 text-teal-700 dark:bg-teal-950/40 dark:text-teal-300"
              )}
              onClick={() => setShowLandmarks((s) => ({ ...s, metro: !s.metro }))}
            >
              <TrainFront className="size-4" /> Metro
            </Button>
            {/* Everyday categories — one chip each; toggling any of them
                reveals the shared clustered places layer (see the landmark
                layers effect). Kept compact so the toolbar doesn't grow. */}
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
                // Everyday places only appear as individual dots when zoomed
                // in enough (they share one clustered source at low zoom) —
                // say so in the tooltip so the layer never feels "broken".
                title="Zoom in to see individual places"
                className={cn(
                  "gap-1.5 rounded-lg",
                  showLandmarks[kind] &&
                    "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300"
                )}
                onClick={() => setShowLandmarks((s) => ({ ...s, [kind]: !s[kind] }))}
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
              onClick={() => setShowAreas((a) => !a)}
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
              onClick={() => {
                // Heatmap and clustering are two views of the same rooms —
                // turning one on turns the other off so they never fight
                // for the same layer stack.
                setHeatmap((h) => !h);
                setClustering(false);
              }}
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
              onClick={() => {
                setClustering((c) => !c);
                setHeatmap(false);
              }}
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
              onClick={() => setShowTravel((t) => !t)}
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
              onClick={() => setListOpen((o) => !o)}
            >
              <ListIcon className="size-4" /> List
            </Button>
            <Button
              variant="ghost"
              size="sm"
              aria-pressed={!!intelMode}
              className={cn(
                "gap-1.5 rounded-lg",
                intelMode &&
                  "bg-violet-50 text-violet-700 dark:bg-violet-950/40 dark:text-violet-300"
              )}
              onClick={() => setIntelMode((m) => (m ? null : "ai"))}
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

          {/* Area count chips — tap to fly there and search near it */}
          {!radiusCenter && areaChips.length > 0 && (
            <div className="flex max-w-sm flex-wrap gap-1.5">
              {areaChips.map((chip) => (
                <button
                  key={chip.area}
                  onClick={() => {
                    if (chip.lat == null || chip.lng == null) return;
                    setRadiusCenter({ lat: chip.lat, lng: chip.lng, label: chip.area });
                    mapRef.current?.flyTo({ center: [chip.lng, chip.lat], zoom: 13 });
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

        {/* Loading badge + share-link button */}
        <div className="absolute right-4 top-4 z-10 flex flex-col items-end gap-2">
          {isLoading && (
            <Badge className="animate-pulse bg-white/90 text-gray-700 shadow dark:bg-gray-900/90 dark:text-gray-300">
              Loading rooms…
            </Badge>
          )}
          <button
            onClick={() => {
              // Build the share link from the LIVE map state, not the URL bar:
              // the URL-sync effect only runs after a map move, so on a fresh
              // load the address may still be bare /map. Building from the map
              // guarantees a copied link always carries the exact view.
              const map = mapRef.current;
              if (!map) return;
              const c = map.getCenter();
              const url =
                window.location.origin +
                window.location.pathname +
                buildMapViewUrl({
                  center: { lat: c.lat, lng: c.lng },
                  zoom: map.getZoom(),
                  radiusKm: radiusCenter ? radiusKm : null,
                  label: radiusCenter?.label ?? null,
                  roomId: activeRoomId,
                  area: selectedArea?.name ?? null,
                  near: nearbyFilter?.kind ?? null,
                  distanceKm: nearbyFilter?.distanceKm ?? null,
                });
              const done = () => {
                setShareCopied(true);
                window.setTimeout(() => setShareCopied(false), 1800);
              };
              // Clipboard API needs a secure context (https or localhost) —
              // fall back to a temporary textarea copy on plain http.
              if (navigator.clipboard?.writeText) {
                void navigator.clipboard.writeText(url).then(done, () => fallbackCopy(url, done));
              } else {
                fallbackCopy(url, done);
              }
            }}
            aria-label="Copy link to this map view"
            title="Copy link to this map view"
            className="flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white/95 px-2.5 py-1.5 text-xs font-medium text-gray-600 shadow backdrop-blur transition-colors hover:border-blue-300 hover:bg-blue-50 hover:text-blue-700 dark:border-gray-700 dark:bg-gray-900/95 dark:text-gray-300 dark:hover:border-blue-600 dark:hover:bg-blue-950/40 dark:hover:text-blue-300"
          >
            {shareCopied ? (
              <>
                <Check className="size-3.5 text-green-600 dark:text-green-400" />
                Copied!
              </>
            ) : (
              <>
                <Share2 className="size-3.5" />
                Share
              </>
            )}
          </button>
        </div>

        {/* Room count summary — authoritative server count (not capped by pagination) */}
        <div className="absolute bottom-4 left-4 z-10 flex items-center gap-2">
          <Badge className="gap-1.5 bg-white/95 px-3 py-1.5 text-sm shadow dark:bg-gray-900/95">
            <MapIcon className="size-3.5" />
            {badgeLabel}
            {counts.avg != null && (
              <span className="text-gray-500 dark:text-gray-400">
                · avg ৳{counts.avg.toLocaleString()}
              </span>
            )}
          </Badge>
        </div>

        {/* Legend — switches to the heatmap scale when the price heatmap is
            on; otherwise lists what's ACTUALLY rendered: rental tiers always,
            area boundaries when enabled, and each landmark category only
            while its toggle is on (no unexplained entries). Visible on mobile
            too (the map list sheet only covers it when open). */}
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
              {/* Area boundary bubbles — main / sub / neighbourhood rings. */}
              {showAreas && (
                <div className="mt-1.5 flex items-center gap-1.5 text-gray-600 dark:text-gray-400">
                  <span className="inline-block h-0.5 w-4 rounded bg-[#ea580c] dark:bg-[#fb923c]" />
                  Area
                </div>
              )}
              {/* Landmark categories — shown only while their layer is on.
                  Consistent lucide iconography (same icons as the toolbar
                  toggles), not emoji — one visual language across controls
                  and legend. */}
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
              {(showLandmarks.metro || showTravel) && (
                <div className="flex items-center gap-1.5 text-gray-600 dark:text-gray-400">
                  <span className="inline-block h-0.5 w-4 rounded bg-[#0d9488] dark:bg-[#2dd4bf]" />
                  MRT Line 6
                </div>
              )}
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
                        // Match the dot colour the map actually renders in
                        // this theme (brighter on the dark basemap).
                        color: darkMode
                          ? LANDMARK_KIND_META[kind].darkColor
                          : LANDMARK_KIND_META[kind].color,
                      }}
                    />
                    {label}
                  </div>
                ) : null
              )}
              {/* Zoom-dependency hint (Phase 7 v3): an everyday landmark
                  category shares one clustered source — at low zoom you see
                  count bubbles, not individual dots. Say so instead of
                  looking broken. */}
              {(() => {
                const everydayOn = (
                  ["hospital", "market", "park", "mosque", "bus_terminal"] as const
                )
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

        {/* Intelligent Map panel — AI search / area intel / commute */}
        <MapIntelPanel
          open={!!intelMode}
          mode={intelMode}
          onMode={setIntelMode}
          onClose={() => setIntelMode(null)}
          rooms={rooms}
          onFlyTo={(lat, lng, zoom = 14) => mapRef.current?.flyTo({ center: [lng, lat], zoom })}
          onSetRadius={(lat, lng, label, km = radiusKm) => {
            setRadiusCenter({ lat, lng, label });
            setRadiusKm(km);
          }}
          selectedArea={selectedIntelArea}
          onSelectArea={setSelectedIntelArea}
          dark={darkMode}
          destination={destination}
          onSetDestination={setDestination}
          pickDestination={pickDestination}
          onTogglePick={() => setPickDestination((p) => !p)}
        />

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
          nearbyFilter={nearbyFilter}
          onNearbyFilterChange={setNearbyFilter}
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
            nearbyFilter={nearbyFilter}
            onNearbyFilterChange={setNearbyFilter}
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

/**
 * Clipboard fallback for non-secure contexts (plain http) where
 * navigator.clipboard is unavailable — a temporary textarea + execCommand.
 */
function fallbackCopy(text: string, onDone: () => void) {
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
    onDone();
  } catch {
    // Copy failed (e.g. blocked) — surface the URL in the address bar instead.
    window.prompt("Copy this map link:", text);
  }
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
  /** Landmark-nearby search — the list can filter rooms by "near a metro /
   * university / … within N km" without touching the map. */
  nearbyFilter: { kind: LandmarkKind; distanceKm: number } | null;
  onNearbyFilterChange: (next: { kind: LandmarkKind; distanceKm: number } | null) => void;
}

const NEARBY_KIND_OPTIONS: { kind: LandmarkKind; label: string }[] = [
  { kind: "metro", label: "Metro station" },
  { kind: "university", label: "University" },
  { kind: "hospital", label: "Hospital" },
  { kind: "market", label: "Market" },
  { kind: "park", label: "Park" },
  { kind: "mosque", label: "Mosque" },
  { kind: "bus_terminal", label: "Bus stop" },
];

const NEARBY_DISTANCES = [0.5, 1, 2];

function MapSidebar({
  rooms,
  loading,
  activeId,
  onSelect,
  onClose,
  nearbyFilter,
  onNearbyFilterChange,
}: MapSidebarProps) {
  const sorted = useMemo(() => sortRoomsForList(rooms), [rooms]);
  // NB: the global Map ctor is shadowed by this module's `Map` component,
  // so reference it explicitly through globalThis.
  const itemRefs = useRef<globalThis.Map<number, HTMLButtonElement>>(new globalThis.Map());

  // Map → list sync: when a marker/popup selects a room, scroll the matching
  // list item into view so both panels agree (guarded against the auto-scroll
  // fighting a user-initiated scroll on first render).
  useEffect(() => {
    if (activeId == null) return;
    const el = itemRefs.current.get(activeId);
    el?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [activeId, sorted]);

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
      {/* Landmark-nearby search — filter the list (and map) by proximity to a
          category of place, without touching the map itself. The selected
          kind/distance flow up to the Map filters via onNearbyFilterChange. */}
      <div className="flex flex-wrap items-center gap-1.5 border-b border-gray-200 px-3 py-2 dark:border-gray-800">
        <span className="text-xs font-medium text-gray-500 dark:text-gray-400">Near</span>
        <select
          aria-label="Nearby landmark category"
          value={nearbyFilter?.kind ?? ""}
          onChange={(e) => {
            const kind = e.target.value as LandmarkKind | "";
            onNearbyFilterChange(kind ? { kind, distanceKm: nearbyFilter?.distanceKm ?? 1 } : null);
          }}
          className="rounded-lg border border-gray-200 bg-card px-2 py-1 text-xs text-foreground dark:border-gray-700"
        >
          <option value="">— anywhere —</option>
          {NEARBY_KIND_OPTIONS.map((o) => (
            <option key={o.kind} value={o.kind}>
              {o.label}
            </option>
          ))}
        </select>
        {nearbyFilter && (
          <>
            <span className="text-xs text-gray-500 dark:text-gray-400">within</span>
            <select
              aria-label="Nearby distance"
              value={nearbyFilter.distanceKm}
              onChange={(e) =>
                onNearbyFilterChange({
                  kind: nearbyFilter.kind,
                  distanceKm: Number(e.target.value),
                })
              }
              className="rounded-lg border border-gray-200 bg-card px-2 py-1 text-xs text-foreground dark:border-gray-700"
            >
              {NEARBY_DISTANCES.map((km) => (
                <option key={km} value={km}>
                  {km} km
                </option>
              ))}
            </select>
            <Button
              variant="ghost"
              size="sm"
              className="size-6 rounded-md p-0 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
              onClick={() => onNearbyFilterChange(null)}
              aria-label="Clear nearby filter"
            >
              <X className="size-3.5" />
            </Button>
          </>
        )}
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
              ref={(el) => {
                if (el) itemRefs.current.set(room.id, el);
                else itemRefs.current.delete(room.id);
              }}
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
