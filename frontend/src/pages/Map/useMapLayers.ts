/**
 * useMapLayers — manages all GeoJSON overlay layers on the map:
 * landmarks, area boundaries, metro route corridor, price heatmap,
 * room clustering, radius circle, travel-time overlay, and the
 * dark-theme paint swap.
 *
 * Extracted from the monolithic Map.tsx so the layer management is
 * independently testable and the main component stays focused on
 * orchestration. Each effect is self-contained and guarded against
 * the map not being ready or sources already existing.
 */

import { useEffect, type RefObject } from "react";
import * as maplibregl from "maplibre-gl";
import {
  areaBoundaryFillOpacity,
  areaBoundaryLineColor,
  AREA_LABEL_MINZOOM,
  boundaryLabelsToFeatureCollection,
  landmarkMinzoom,
  LANDMARK_KIND_META,
  THEME_PAINTS,
  themePaintValue,
  TRAVEL_BAND_DARK_OPACITY,
  TRAVEL_BAND_LIGHT_OPACITY,
} from "../../lib/mapInteractions";
import {
  haversineKm,
  landmarkToFeature,
  landmarksToFeatureCollection,
  metroRouteFeatureCollection,
  roomsToFeatureCollection,
  travelIsochrones,
} from "../../lib/mapUtils";
import { useUiStore } from "../../stores/uiStore";
import type { LandmarkKind, Room } from "../../types";
import type { MapLayerId } from "./MapToolbar";

interface MapLayersState {
  mapRef: RefObject<maplibregl.Map | null>;
  mapReady: boolean;
  landmarks: { key: string; name: string; kind: LandmarkKind; lat: number; lng: number }[];
  boundaries: unknown;
  rooms: Room[];
  clustering: boolean;
  showLandmarks: Record<MapLayerId, boolean>;
  showAreas: boolean;
  heatmap: boolean;
  showTravel: boolean;
  radiusCenter: { lat: number; lng: number; label: string } | null;
  radiusKm: number;
  darkMode: boolean;
}

export function useMapLayers({
  mapRef,
  mapReady,
  landmarks,
  boundaries,
  rooms,
  clustering,
  showLandmarks,
  showAreas,
  heatmap,
  showTravel,
  radiusCenter,
  radiusKm,
  darkMode,
}: MapLayersState) {
  // ---- GeoJSON layers (landmarks) -----------------------------------------
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

    const DOT_LAYER: Record<LandmarkKind, string> = {
      university: "universities",
      metro: "metro",
      hospital: "places-hospital",
      market: "places-market",
      park: "places-park",
      mosque: "places-mosque",
      bus_terminal: "places-bus-terminal",
    };

    // Universities + metro: simple dot layers.
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
      (["hospital", "market", "park", "mosque", "bus_terminal"] as const).forEach((kind) => {
        const id = DOT_LAYER[kind];
        const meta = LANDMARK_KIND_META[kind];
        if (map.getLayer(id)) return;
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
      // Layer juggling — safe to ignore.
    }
  }, [landmarks, mapReady]);

  // ---- area boundary polygons + labels -------------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || !boundaries) return;
    const SOURCE = "area-boundaries";
    const LABEL_SOURCE = "area-labels";
    const dark = useUiStore.getState().darkMode;
    try {
      if (!map.getSource(SOURCE)) {
        map.addSource(SOURCE, {
          type: "geojson",
          data: boundaries as GeoJSON.FeatureCollection,
          promoteId: "key",
        });
        const spec = [
          {
            id: "area-boundary-fill-main",
            kind: "main_area" as const,
            type: "fill" as const,
            minzoom: 9.5,
            paint: {
              "fill-color": "#f97316",
              "fill-opacity": areaBoundaryFillOpacity("main_area", dark),
            },
          },
          {
            id: "area-boundary-line-main",
            kind: "main_area" as const,
            type: "line" as const,
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
              ] as unknown as number,
              "line-opacity": 0.75,
            },
          },
          {
            id: "area-boundary-fill-sub",
            kind: "sub_area" as const,
            type: "fill" as const,
            minzoom: 11.5,
            paint: {
              "fill-color": "#3b82f6",
              "fill-opacity": areaBoundaryFillOpacity("sub_area", dark),
            },
          },
          {
            id: "area-boundary-line-sub",
            kind: "sub_area" as const,
            type: "line" as const,
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
              ] as unknown as number,
              "line-opacity": 0.6,
            },
          },
          {
            id: "area-boundary-fill-nbhd",
            kind: "neighborhood" as const,
            type: "fill" as const,
            minzoom: 13.5,
            paint: {
              "fill-color": "#7c3aed",
              "fill-opacity": areaBoundaryFillOpacity("neighborhood", dark),
            },
          },
          {
            id: "area-boundary-line-nbhd",
            kind: "neighborhood" as const,
            type: "line" as const,
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
              ] as unknown as number,
              "line-opacity": 0.5,
            },
          },
        ];
        spec.forEach(({ id, kind, type, minzoom, paint }) => {
          map.addLayer(
            {
              ...{ type },
              id,
              source: SOURCE,
              filter: ["==", ["get", "kind"], kind],
              minzoom,
              paint,
            } as maplibregl.LayerSpecification,
            map.getLayer("rooms-clusters-layer") ? "rooms-clusters-layer" : undefined
          );
        });
      }
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
                "text-font": ["Noto Sans Regular"],
                "text-anchor": "center",
                "text-letter-spacing": 0.02,
              },
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
    } catch {
      // Layer juggling — safe to ignore.
    }
  }, [boundaries, mapReady]);

  // ---- layer visibility ---------------------------------------------------
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
    [
      "places-clusters-layer",
      "places-clusters-count",
      "places-hospital",
      "places-market",
      "places-park",
      "places-mosque",
      "places-bus-terminal",
    ].forEach((id) => {
      if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", placesOn ? "visible" : "none");
    });
    [
      "area-boundary-fill-main",
      "area-boundary-line-main",
      "area-boundary-fill-sub",
      "area-boundary-line-sub",
      "area-boundary-fill-nbhd",
      "area-boundary-line-nbhd",
      "area-label-main",
      "area-label-sub",
      "area-label-nbhd",
    ].forEach((id) => {
      if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", showAreas ? "visible" : "none");
    });
  }, [showLandmarks, showAreas, mapReady]);

  // ---- metro route corridor -----------------------------------------------
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
        [id, casingId].forEach((l) => {
          if (map.getLayer(l)) map.setLayoutProperty(l, "visibility", visible ? "visible" : "none");
        });
      };
      if (map.getLayer(id)) {
        setVisibility();
        (map.getSource(id) as maplibregl.GeoJSONSource).setData(data);
      } else if (data.features.length > 0) {
        map.addSource(id, { type: "geojson", data });
        map.addLayer({
          id: casingId,
          type: "line",
          source: id,
          layout: { "line-cap": "round", "line-join": "round" },
          paint: { "line-color": "#ffffff", "line-width": 8, "line-opacity": 0.55 },
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
      // no-op
    }
  }, [landmarks, mapReady, showLandmarks.metro, showTravel]);

  // ---- heatmap layer ------------------------------------------------------
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
      // no-op
    }
  }, [heatmap, rooms, mapReady]);

  // ---- radius circle ------------------------------------------------------
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
              "circle-radius": [
                "interpolate",
                ["exponential", 2],
                ["zoom"],
                10,
                (radiusKm * 1000 * 2 ** 10) / (156543.03 * 0.914),
                16,
                (radiusKm * 1000 * 2 ** 16) / (156543.03 * 0.914),
              ] as unknown as number,
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
      // no-op
    }
  }, [radiusCenter, radiusKm, mapReady]);

  // ---- travel-time overlay ------------------------------------------------
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
          features: bands.map((band, i) => ({ ...band.feature, properties: { band: i } })),
        });
        const reachId = "metro-reach";
        const reachable = landmarks
          .filter((l) => l.kind === "metro")
          .filter((l) => haversineKm(radiusCenter.lat, radiusCenter.lng, l.lat, l.lng) <= 2.25)
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
      // no-op
    }
  }, [showTravel, radiusCenter, mapReady, landmarks]);

  // ---- dark-theme paint swap ----------------------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const dark = darkMode;
    const set = (
      layer: string,
      prop: Parameters<typeof map.setPaintProperty>[1],
      value: unknown
    ) => {
      if (map.getLayer(layer)) {
        try {
          map.setPaintProperty(layer, prop, value as never);
        } catch {
          /* no-op */
        }
      }
    };
    Object.entries(THEME_PAINTS).forEach(([layer, patches]) => {
      patches.forEach(({ prop, dark: darkVal, light }) => {
        set(layer, prop as Parameters<typeof map.setPaintProperty>[1], dark ? darkVal : light);
      });
    });
    [0, 1, 2].forEach((i) => {
      const id = `travel-bands-${i}`;
      set(id, "fill-opacity", dark ? TRAVEL_BAND_DARK_OPACITY : TRAVEL_BAND_LIGHT_OPACITY);
      if (dark) set(id, "fill-outline-color", "#ffffff");
    });
  }, [darkMode, mapReady, showLandmarks, heatmap, clustering, showTravel, radiusCenter]);
}
