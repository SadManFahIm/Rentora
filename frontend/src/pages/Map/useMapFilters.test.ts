import { describe, expect, it } from "vitest";
import { renderHook } from "@testing-library/react";
import { useMapFilters } from "./useMapFilters";

describe("useMapFilters", () => {
  it("returns empty object when no view state is active", () => {
    const { result } = renderHook(() =>
      useMapFilters({
        debouncedViewbox: null,
        debouncedRadiusCenter: null,
        radiusKm: 2,
        selectedArea: null,
        nearbyFilter: null,
        nearbyLandmarkKey: null,
      })
    );
    expect(result.current).toEqual({});
  });

  it("uses bbox when viewport is active and no radius search", () => {
    const { result } = renderHook(() =>
      useMapFilters({
        debouncedViewbox: "90.3,23.7,90.5,23.9",
        debouncedRadiusCenter: null,
        radiusKm: 2,
        selectedArea: null,
        nearbyFilter: null,
        nearbyLandmarkKey: null,
      })
    );
    expect(result.current.bbox).toBe("90.3,23.7,90.5,23.9");
    expect(result.current.nearLat).toBeUndefined();
  });

  it("uses radius center when radius search is active", () => {
    const center = { lat: 23.75, lng: 90.38, label: "DU" };
    const { result } = renderHook(() =>
      useMapFilters({
        debouncedViewbox: "90.3,23.7,90.5,23.9",
        debouncedRadiusCenter: center,
        radiusKm: 3,
        selectedArea: null,
        nearbyFilter: null,
        nearbyLandmarkKey: null,
      })
    );
    expect(result.current.nearLat).toBe(23.75);
    expect(result.current.nearLng).toBe(90.38);
    expect(result.current.radiusKm).toBe(3);
    expect(result.current.bbox).toBeUndefined();
  });

  it("filters by parent area when a sub-area is selected", () => {
    const { result } = renderHook(() =>
      useMapFilters({
        debouncedViewbox: null,
        debouncedRadiusCenter: null,
        radiusKm: 2,
        selectedArea: { key: "gulshan", name: "Gulshan", kind: "sub_area", parentName: "Dhaka" },
        nearbyFilter: null,
        nearbyLandmarkKey: null,
      })
    );
    expect(result.current.area).toBe("Dhaka");
  });

  it("filters by main area name when no parent", () => {
    const { result } = renderHook(() =>
      useMapFilters({
        debouncedViewbox: null,
        debouncedRadiusCenter: null,
        radiusKm: 2,
        selectedArea: { key: "uttara", name: "Uttara", kind: "main_area", parentName: null },
        nearbyFilter: null,
        nearbyLandmarkKey: null,
      })
    );
    expect(result.current.area).toBe("Uttara");
  });

  it("adds nearLandmark when nearby filter and key are present", () => {
    const { result } = renderHook(() =>
      useMapFilters({
        debouncedViewbox: null,
        debouncedRadiusCenter: null,
        radiusKm: 2,
        selectedArea: null,
        nearbyFilter: { kind: "metro", distanceKm: 1 },
        nearbyLandmarkKey: "mrt_dhanmondi",
      })
    );
    expect(result.current.nearLandmark).toBe("mrt_dhanmondi");
    expect(result.current.radiusKm).toBe(1);
  });

  it("does not add nearLandmark when key is null", () => {
    const { result } = renderHook(() =>
      useMapFilters({
        debouncedViewbox: null,
        debouncedRadiusCenter: null,
        radiusKm: 2,
        selectedArea: null,
        nearbyFilter: { kind: "metro", distanceKm: 1 },
        nearbyLandmarkKey: null,
      })
    );
    expect(result.current.nearLandmark).toBeUndefined();
  });

  it("combines bbox, area, and nearby filters", () => {
    const { result } = renderHook(() =>
      useMapFilters({
        debouncedViewbox: "90.3,23.7,90.5,23.9",
        debouncedRadiusCenter: null,
        radiusKm: 2,
        selectedArea: { key: "uttara", name: "Uttara", kind: "main_area", parentName: null },
        nearbyFilter: { kind: "university", distanceKm: 2 },
        nearbyLandmarkKey: "du",
      })
    );
    expect(result.current.bbox).toBe("90.3,23.7,90.5,23.9");
    expect(result.current.area).toBe("Uttara");
    expect(result.current.nearLandmark).toBe("du");
    expect(result.current.radiusKm).toBe(2);
  });
});
