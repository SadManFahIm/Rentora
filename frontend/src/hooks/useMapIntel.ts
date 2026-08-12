import { useQuery } from "@tanstack/react-query";
import { mapIntelService, mapIntelKeys } from "../services/mapIntelService";

/** Area intelligence for one area or all areas. */
export function useAreaStats(area?: string) {
  return useQuery({
    queryKey: mapIntelKeys.stats(area),
    queryFn: () => mapIntelService.getStats(area),
    staleTime: 10 * 60_000,
  });
}

/** Commute ETA between two points. */
export function useCommute(
  params: {
    from_lat: number;
    from_lng: number;
    to_lat: number;
    to_lng: number;
    mode: "walking" | "driving" | "transit";
  } | null
) {
  return useQuery({
    queryKey: mapIntelKeys.commute(params ?? {}),
    queryFn: () => mapIntelService.getCommute(params!),
    enabled: params !== null,
    staleTime: 5 * 60_000,
  });
}

/** Value scores for a set of room ids (the visible viewport). */
export function useValueScores(ids: number[]) {
  return useQuery({
    queryKey: mapIntelKeys.value(ids),
    queryFn: () => mapIntelService.getValue(ids),
    enabled: ids.length > 0,
    staleTime: 60_000,
  });
}

/** Affordability per area for a budget. */
export function useAffordability(budget: number | null) {
  return useQuery({
    queryKey: mapIntelKeys.affordability(budget ?? 0),
    queryFn: () => mapIntelService.getAffordability(budget!),
    enabled: budget !== null && budget > 0,
    staleTime: 10 * 60_000,
  });
}

/** Ideal-area recommendations from a user profile. */
export function useIdealAreas(
  params: {
    budget: number;
    work_lat?: number;
    work_lng?: number;
    max_commute?: number;
    room_type?: string;
  } | null
) {
  return useQuery({
    queryKey: mapIntelKeys.ideal(params ?? {}),
    queryFn: () => mapIntelService.getIdealAreas(params!),
    enabled: params !== null,
    staleTime: 10 * 60_000,
  });
}
