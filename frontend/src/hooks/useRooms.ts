import { useQuery } from "@tanstack/react-query";
import { roomService } from "../services/roomService";
import type { Room, RoomFilters } from "../types";

// ============================================================
// ROOM QUERY HOOKS
// ============================================================

export const roomKeys = {
  all: ["rooms"] as const,
  list: (filters: RoomFilters) => [...roomKeys.all, "list", filters] as const,
  detail: (id: number) => [...roomKeys.all, "detail", id] as const,
};

/** Fetch the room list, optionally filtered (server-side). */
export function useRooms(filters: RoomFilters = {}) {
  return useQuery<Room[]>({
    queryKey: roomKeys.list(filters),
    queryFn: () => roomService.getRooms(filters),
    staleTime: 60_000,
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
