/**
 * useMapFilters — computes the room query filters from the map view state.
 *
 * Extracted from the monolithic Map.tsx so the filter logic is
 * independently testable. The filters determine what rooms the
 * backend returns: bbox-based viewport, radius search, area boundary
 * click, or landmark-nearby proximity.
 */

import { useMemo } from "react";
import type { AreaKind, LandmarkKind } from "../../types";

interface FilterState {
  debouncedViewbox: string | null;
  debouncedRadiusCenter: { lat: number; lng: number; label: string } | null;
  radiusKm: number;
  selectedArea: { key: string; name: string; kind: AreaKind; parentName: string | null } | null;
  nearbyFilter: { kind: LandmarkKind; distanceKm: number } | null;
  nearbyLandmarkKey: string | null;
}

export function useMapFilters({
  debouncedViewbox,
  debouncedRadiusCenter,
  radiusKm,
  selectedArea,
  nearbyFilter,
  nearbyLandmarkKey,
}: FilterState) {
  return useMemo(() => {
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
}
