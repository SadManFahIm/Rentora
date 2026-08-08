import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { roomService } from "../services/roomService";
import type {
  CreateRoomPayload,
  GeocodeSuggestion,
  Landmark,
  MapSummary,
  Room,
  RoomFilters,
  TierCatalog,
} from "../types";

// ============================================================
// ROOM QUERY HOOKS
// ============================================================

export const roomKeys = {
  all: ["rooms"] as const,
  list: (filters: RoomFilters) => [...roomKeys.all, "list", filters] as const,
  detail: (id: number) => [...roomKeys.all, "detail", id] as const,
  tierCatalog: () => [...roomKeys.all, "tier-catalog"] as const,
};

/** Fetch the room list, optionally filtered (server-side). */
export function useRooms(filters: RoomFilters = {}) {
  return useQuery<Room[]>({
    queryKey: roomKeys.list(filters),
    queryFn: () => roomService.getRooms(filters),
    staleTime: 60_000,
  });
}

/** Create a new listing (landlord flow). Invalidates the room list cache. */
export function useCreateRoom() {
  const queryClient = useQueryClient();
  return useMutation<Room, Error, CreateRoomPayload>({
    mutationFn: (payload) => roomService.createRoom(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: roomKeys.all });
    },
  });
}

/** Fetch map landmarks (universities + metro stations) for the map view. */
export function useLandmarks() {
  return useQuery<Landmark[]>({
    queryKey: [...roomKeys.all, "landmarks"] as const,
    queryFn: () => roomService.getLandmarks(),
    staleTime: 24 * 60 * 60 * 1000, // static data ΓÇö cache for a day
  });
}

/** Fetch a single room by id. */
export function useRoom(id: number | null | undefined) {
  return useQuery<Room>({
    queryKey: roomKeys.detail(id ?? -1),
    queryFn: () => roomService.getRoomById(id as number),
    enabled: id != null,
  });
}

/** Street/area/landmark autocomplete for the map search box (debounced by caller). */
export function useGeocode(query: string) {
  const trimmed = query.trim();
  return useQuery<GeocodeSuggestion[]>({
    queryKey: [...roomKeys.all, "geocode", trimmed] as const,
    queryFn: () => roomService.geocode(trimmed),
    enabled: trimmed.length >= 2,
    staleTime: 5 * 60_000,
  });
}

/** Aggregate room counts for the map badge (cheap COUNT/AVG, same geo filters). */
export function useMapSummary(filters: RoomFilters = {}) {
  return useQuery<MapSummary>({
    queryKey: [...roomKeys.all, "summary", filters] as const,
    queryFn: () => roomService.getMapSummary(filters),
    staleTime: 30_000,
  });
}

/** Public paid-listing tier catalog (pricing + benefits). */
export function useTierCatalog() {
  return useQuery<TierCatalog>({
    queryKey: roomKeys.tierCatalog(),
    queryFn: () => roomService.getTierCatalog(),
    staleTime: 10 * 60_000,
  });
}
