import { api } from "./api";
import { mapRoom, type ApiRoom, type Paginated } from "./mappers";
import type {
  GeocodeSuggestion,
  Room,
  RoomFilters,
  CreateRoomPayload,
  TierCatalog,
  Landmark,
  MapSummary,
} from "../types";

// ============================================================
// ROOM SERVICE ΓÇö real /rooms/ endpoints
// ============================================================

/** Translate UI filters into the backend's query parameters. */
function buildParams(filters: RoomFilters): Record<string, string> {
  const params: Record<string, string> = {};

  if (filters.query) params.search = filters.query;
  if (filters.area && filters.area !== "All") params.area = filters.area;
  if (filters.type && filters.type !== "All") params.room_type = filters.type.toLowerCase();
  if (filters.gender && filters.gender !== "Any")
    params.gender_preference = filters.gender.toLowerCase();
  if (filters.minPrice) params.price__gte = filters.minPrice;
  if (filters.maxPrice) params.price__lte = filters.maxPrice;
  if (filters.available === "yes") params.is_available = "true";
  if (filters.owner != null) params.owner = String(filters.owner);

  // Geo / map queries (Phase 7) ΓÇö the backend supports bbox and a reference
  // point (near_lat/near_lng or near_landmark) with radius_km.
  if (filters.bbox) params.bbox = filters.bbox;
  if (filters.nearLat != null) params.near_lat = String(filters.nearLat);
  if (filters.nearLng != null) params.near_lng = String(filters.nearLng);
  if (filters.radiusKm != null) params.radius_km = String(filters.radiusKm);

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

  /** GET /rooms/landmarks/ ΓÇö public map landmark layers (universities + metro). */
  async getLandmarks(): Promise<Landmark[]> {
    const { data } =
      await api.get<{ key: string; name: string; kind: string; lat: number; lng: number }[]>(
        "/rooms/landmarks/"
      );
    return data.map((l) => ({
      key: l.key,
      name: l.name,
      kind: l.kind === "university" ? "university" : "metro",
      lat: l.lat,
      lng: l.lng,
    }));
  },

  /** GET /rooms/:id/ */
  async getRoomById(id: number): Promise<Room> {
    const { data } = await api.get<ApiRoom>(`/rooms/${id}/`);
    return mapRoom(data);
  },

  /** GET /rooms/geocode/ ΓÇö street/area/landmark autocomplete for the map search box. */
  async geocode(query: string): Promise<GeocodeSuggestion[]> {
    const { data } = await api.get<
      { key: string; label: string; kind: string; lat: number; lng: number }[]
    >("/rooms/geocode/", { params: { q: query } });
    return data.map((s) => ({
      key: s.key,
      label: s.label,
      kind: s.kind as GeocodeSuggestion["kind"],
      lat: Number(s.lat),
      lng: Number(s.lng),
    }));
  },

  /**
   * GET /rooms/summary/ ΓÇö aggregate room counts for the current map viewport
   * (total/available/price stats), so the map badge doesn't need the full
   * paginated list. Accepts the same geo filters as getRooms.
   */
  async getMapSummary(filters: RoomFilters = {}): Promise<MapSummary> {
    const { data } = await api.get<MapSummary>("/rooms/summary/", {
      params: buildParams(filters),
    });
    return data;
  },

  /** GET /rooms/tier-catalog/ ΓÇö public paid-tier pricing/benefits. */
  async getTierCatalog(): Promise<TierCatalog> {
    const { data } = await api.get<{
      tiers: {
        tier: string;
        label: string;
        price: number;
        benefits: string[];
      }[];
      duration_days: number;
      currency: string;
    }>("/rooms/tier-catalog/");
    return {
      tiers: data.tiers.map((t) => ({
        tier: t.tier as TierCatalog["tiers"][number]["tier"],
        label: t.label,
        price: Number(t.price),
        benefits: t.benefits,
      })),
      durationDays: data.duration_days,
      currency: data.currency,
    };
  },

  /** POST /rooms/ ΓÇö create a listing (landlord). */
  async createRoom(payload: CreateRoomPayload): Promise<Room> {
    const body = {
      title: payload.name,
      description: payload.description,
      room_type: payload.type.toLowerCase(),
      price: payload.price,
      area: payload.area,
      // Backend requires an address; the area label keeps it meaningful until
      // a full street-address field is added to the listing form.
      address: `${payload.area}, Dhaka`,
      lat: payload.lat,
      lng: payload.lng,
      amenities: payload.amenities,
      gender_preference: payload.gender.toLowerCase(),
      size_sqft: payload.size,
      is_available: payload.available,
    };
    const { data } = await api.post<ApiRoom>("/rooms/", body);
    return mapRoom(data);
  },
};

export default roomService;
