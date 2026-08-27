/**
 * useMapUrl — keeps the browser URL in sync with the map view state.
 *
 * Extracted from the monolithic Map.tsx so the URL-sync logic is
 * independently testable and the main component stays focused on
 * map orchestration.
 *
 * The URL carries: center, zoom, radius, area, nearby-landmark filters,
 * and active room id — so sharing a link always opens the exact same view.
 */

import { useEffect, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import { buildMapViewUrl } from "../../lib/mapUtils";
import type { LandmarkKind } from "../../types";

interface MapUrlState {
  mapReady: boolean;
  mapRef: {
    current: { getCenter: () => { lat: number; lng: number }; getZoom: () => number } | null;
  };
  radiusCenter: { lat: number; lng: number; label: string } | null;
  radiusKm: number;
  activeRoomId: number | null;
  selectedArea: { name: string } | null;
  nearbyFilter: { kind: LandmarkKind; distanceKm: number } | null;
  debouncedViewbox: string | null;
}

export function useMapUrl({
  mapReady,
  mapRef,
  radiusCenter,
  radiusKm,
  activeRoomId,
  selectedArea,
  nearbyFilter,
  debouncedViewbox,
}: MapUrlState) {
  const [, setSearchParams] = useSearchParams();
  const urlAppliedRef = useRef(false);

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

  return { urlAppliedRef };
}
