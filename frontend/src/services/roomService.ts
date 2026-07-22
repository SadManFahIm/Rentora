import type { ApiResponse } from "./api";
// import { api } from "./api"; // ← enable in Phase 3 for real HTTP calls
import { mockRooms } from "../data/mockData";
import type {
  Room,
  RoomFilters,
  CreateRoomPayload,
  UpdateRoomPayload,
} from "../types";

// ============================================================
// ROOM SERVICE
// Mock implementation backed by mockData. In Phase 3 each method
// becomes a real `api.get/post/...` call returning the same shape.
// ============================================================

/** Simulate network latency so loading states are observable. */
const delay = (ms = 250) => new Promise((r) => setTimeout(r, ms));

const wrap = <T>(data: T, meta?: Record<string, unknown>): ApiResponse<T> => ({
  data,
  meta,
});

/** Apply the UI filter set to a room list (mock server-side filtering). */
function applyFilters(rooms: Room[], filters: RoomFilters = {}): Room[] {
  let result = rooms.filter((r) => {
    const q = filters.query?.toLowerCase();
    if (
      q &&
      !r.name.toLowerCase().includes(q) &&
      !r.area.toLowerCase().includes(q)
    )
      return false;
    if (filters.area && filters.area !== "All" && r.area !== filters.area)
      return false;
    if (filters.type && filters.type !== "All" && r.type !== filters.type)
      return false;
    if (filters.minPrice && r.price < parseInt(filters.minPrice)) return false;
    if (filters.maxPrice && r.price > parseInt(filters.maxPrice)) return false;
    if (
      filters.amenities?.length &&
      !filters.amenities.every((a) => r.amenities.includes(a))
    )
      return false;
    if (
      filters.gender &&
      filters.gender !== "Any" &&
      r.gender !== "Any" &&
      r.gender !== filters.gender
    )
      return false;
    if (filters.available === "yes" && !r.available) return false;
    return true;
  });

  switch (filters.sort) {
    case "price-asc":
      result = [...result].sort((a, b) => a.price - b.price);
      break;
    case "price-desc":
      result = [...result].sort((a, b) => b.price - a.price);
      break;
    case "rating":
      result = [...result].sort((a, b) => b.rating - a.rating);
      break;
    default:
      break;
  }

  return result;
}

export const roomService = {
  async getRooms(filters: RoomFilters = {}): Promise<ApiResponse<Room[]>> {
    await delay();
    const rooms = applyFilters(mockRooms, filters);
    return wrap(rooms, { total: rooms.length });
    // Phase 3: return (await api.get<ApiResponse<Room[]>>("/rooms", { params: filters })).data;
  },

  async getRoomById(id: number): Promise<ApiResponse<Room>> {
    await delay();
    const room = mockRooms.find((r) => r.id === id);
    if (!room) {
      throw new Error(`Room ${id} not found`);
    }
    return wrap(room);
    // Phase 3: return (await api.get<ApiResponse<Room>>(`/rooms/${id}`)).data;
  },

  async createRoom(payload: CreateRoomPayload): Promise<ApiResponse<Room>> {
    await delay();
    const room: Room = {
      ...payload,
      id: Math.max(0, ...mockRooms.map((r) => r.id)) + 1,
      rating: 0,
      reviews: 0,
    };
    return wrap(room);
    // Phase 3: return (await api.post<ApiResponse<Room>>("/rooms", payload)).data;
  },

  async updateRoom(
    id: number,
    payload: UpdateRoomPayload
  ): Promise<ApiResponse<Room>> {
    await delay();
    const existing = mockRooms.find((r) => r.id === id);
    if (!existing) {
      throw new Error(`Room ${id} not found`);
    }
    return wrap({ ...existing, ...payload });
    // Phase 3: return (await api.patch<ApiResponse<Room>>(`/rooms/${id}`, payload)).data;
  },

  async deleteRoom(id: number): Promise<ApiResponse<{ id: number }>> {
    await delay();
    return wrap({ id });
    // Phase 3: return (await api.delete<ApiResponse<{ id: number }>>(`/rooms/${id}`)).data;
  },
};

export default roomService;
