import { api } from "./api";
import { mapRoom, type ApiRoom, type Paginated } from "./mappers";
import type { Room, RoomFilters, CreateRoomPayload } from "../types";

// ============================================================
// ROOM SERVICE — real /rooms/ endpoints
// ============================================================

/** Translate UI filters into the backend's query parameters. */
function buildParams(filters: RoomFilters): Record<string, string> {
  const params: Record<string, string> = {};

  if (filters.query) params.search = filters.query;
  if (filters.area && filters.area !== "All") params.area = filters.area;
  if (filters.type && filters.type !== "All")
    params.room_type = filters.type.toLowerCase();
  if (filters.gender && filters.gender !== "Any")
    params.gender_preference = filters.gender.toLowerCase();
  if (filters.minPrice) params.price__gte = filters.minPrice;
  if (filters.maxPrice) params.price__lte = filters.maxPrice;
  if (filters.available === "yes") params.is_available = "true";

  switch (filters.sort) {
    case "price-asc":
      params.ordering = "price";
      break;
    case "price-desc":
      params.ordering = "-price";
      break;
    case "rating":
      params.ordering = "-rating";
      break;
    default:
      break;
  }

  return params;
}

export const roomService = {
  /**
   * GET /rooms/ with server-side filtering, sorting and search.
   * Amenities are filtered client-side (the backend has no amenities filter).
   */
  async getRooms(filters: RoomFilters = {}): Promise<Room[]> {
    const { data } = await api.get<Paginated<ApiRoom>>("/rooms/", {
      params: buildParams(filters),
    });
    let rooms = data.results.map(mapRoom);

    if (filters.amenities && filters.amenities.length > 0) {
      const wanted = filters.amenities;
      rooms = rooms.filter((r) => wanted.every((a) => r.amenities.includes(a)));
    }

    return rooms;
  },

  /** GET /rooms/:id/ */
  async getRoomById(id: number): Promise<Room> {
    const { data } = await api.get<ApiRoom>(`/rooms/${id}/`);
    return mapRoom(data);
  },

  /** POST /rooms/ — create a listing (landlord). */
  async createRoom(payload: CreateRoomPayload): Promise<Room> {
    const body = {
      title: payload.name,
      description: payload.description,
      room_type: payload.type.toLowerCase(),
      price: payload.price,
      area: payload.area,
      lat: payload.lat,
      lng: payload.lng,
      amenities: payload.amenities,
      gender_preference: payload.gender.toLowerCase(),
      size_sqft: payload.size,
      is_available: payload.available,
      is_featured: payload.featured,
    };
    const { data } = await api.post<ApiRoom>("/rooms/", body);
    return mapRoom(data);
  },
};

export default roomService;
