import { useQuery } from "@tanstack/react-query";
import { roomService } from "../services/roomService";
import type { Landmark, Room, RoomFilters, TierCatalog } from "../types";

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

/** Fetch map landmarks (universities + metro stations) for the map view. */
export function useLandmarks() {
  return useQuery<Landmark[]>({
    queryKey: [...roomKeys.all, "landmarks"] as const,
    queryFn: () => roomService.getLandmarks(),
    staleTime: 24 * 60 * 60 * 1000, // static data — cache for a day
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

/** Public paid-listing tier catalog (pricing + benefits). */
export function useTierCatalog() {
  return useQuery<TierCatalog>({
    queryKey: roomKeys.tierCatalog(),
    queryFn: () => roomService.getTierCatalog(),
    staleTime: 10 * 60_000,
  });
}
