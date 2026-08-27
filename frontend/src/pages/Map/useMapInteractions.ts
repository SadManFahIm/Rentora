/**
 * useMapInteractions — click/hover wiring for landmark, metro, heatmap,
 * and walking-isochrone layers.
 *
 * Extracted from the monolithic Map.tsx so the interaction logic is
 * independently testable and the main component stays focused on
 * map orchestration. Registered ONCE per map instance (MapLibre .on()
 * does not dedupe).
 */

import { useEffect, useRef } from "react";
import * as maplibregl from "maplibre-gl";
import {
  areaStats,
  heatmapPopupHtml,
  isochronePopupHtml,
  isochroneStats,
  landmarkPopupHtml,
  LANDMARK_KIND_META,
  metroRoutePopupHtml,
  nearbyStats,
} from "../../lib/mapInteractions";
import type { LandmarkKind, Room } from "../../types";

interface MapInteractionsState {
  mapRef: React.RefObject<maplibregl.Map | null>;
  mapReady: boolean;
  roomsRef: React.RefObject<Room[]>;
  radiusCenterRef: React.RefObject<{ lat: number; lng: number; label: string } | null>;
  setRadiusCenter: (center: { lat: number; lng: number; label: string } | null) => void;
  setRadiusKm: (km: number) => void;
}

export function useMapInteractions({
  mapRef,
  mapReady,
  roomsRef,
  radiusCenterRef,
  setRadiusCenter,
  setRadiusKm,
}: MapInteractionsState) {
  const interactionHandlersRef = useRef<maplibregl.Map | null>(null);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    if (interactionHandlersRef.current === map) return;
    interactionHandlersRef.current = map;
    const m = map;

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
      const stats = nearbyStats(roomsRef.current ?? [], lat, lng, 2);
      const popup = new maplibregl.Popup({
        closeButton: false,
        closeOnClick: true,
        maxWidth: "260px",
      })
        .setLngLat(e.lngLat)
        .setHTML(landmarkPopupHtml(kind, name, stats, kindCta(kind)))
        .addTo(m);
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

    const landmarkCoords = (f: GeoJSON.Feature): [number, number] => {
      const c = (f.geometry as GeoJSON.Point).coordinates;
      return [Number(c[1]), Number(c[0])];
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

    // Everyday categories.
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

    // Places cluster bubble → zoom in.
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

    // MRT Line-6 corridor.
    map.on("click", "metro-route", (e) => {
      new maplibregl.Popup({ closeButton: false, closeOnClick: true, maxWidth: "240px" })
        .setLngLat(e.lngLat)
        .setHTML(metroRoutePopupHtml())
        .addTo(m);
    });
    map.on("mouseenter", "metro-route", pointer(true));
    map.on("mouseleave", "metro-route", pointer(false));

    // Price heatmap.
    map.on("click", "price-heatmap", (e) => {
      const f = e.features?.[0];
      if (!f) return;
      const area = String((f.properties ?? {}).area ?? "");
      const stats = areaStats(roomsRef.current ?? [], area);
      new maplibregl.Popup({ closeButton: false, closeOnClick: true, maxWidth: "240px" })
        .setLngLat(e.lngLat)
        .setHTML(heatmapPopupHtml(area, stats))
        .addTo(m);
    });
    map.on("mouseenter", "price-heatmap", pointer(true));
    map.on("mouseleave", "price-heatmap", pointer(false));

    // Walking isochrone bands.
    const BAND_MINUTES = [10, 20, 30];
    const showBandStats = (band: number, e: maplibregl.MapMouseEvent) => {
      const center = radiusCenterRef.current;
      if (!center) return;
      const minutes = BAND_MINUTES[band];
      const radius = (minutes / 60) * 4.5;
      const stats = isochroneStats(roomsRef.current ?? [], center, radius);
      new maplibregl.Popup({ closeButton: false, closeOnClick: true, maxWidth: "240px" })
        .setLngLat(e.lngLat)
        .setHTML(isochronePopupHtml(minutes, stats))
        .addTo(m);
    };
    ["travel-bands-0", "travel-bands-1", "travel-bands-2"].forEach((id, i) => {
      m.on("click", id, (e) => showBandStats(i, e));
      m.on("mouseenter", id, pointer(true));
      m.on("mouseleave", id, pointer(false));
    });
  }, [mapReady]);
}
