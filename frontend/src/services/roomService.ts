import { api } from "./api";
import { mapRoom, type ApiRoom, type Paginated } from "./mappers";
import {
  buildCacheKey,
  cacheFresh,
  filterCachedRooms,
  getCachedRoom,
  getCachedRooms,
  ROOMS_TTL_MS,
  ROOM_DETAIL_TTL_MS,
  setCachedRoom,
  setCachedRooms,
} from "../lib/offlineDb";
import { setOfflineCacheStatus } from "../lib/offlineStatus";
import type {
  GeocodeSuggestion,
  NlParsed,
  Room,
  RoomFilters,
  CreateRoomPayload,
  TierCatalog,
  Landmark,
  MapSummary,
  RoomInsights,
  SimilarImageResult,
  SimilarRoomResult,
} from "../types";

interface ApiRoomInsights {
  rooms: {
    id: number;
    title: string;
    price: number;
    area: string;
    room_type: string;
    tier: string;
    verified: boolean;
    views_7d: number;
    views_30d: number;
    views_total: number;
    wishlist_count: number;
    booking_requests: number;
    booking_approved: number;
    area_avg_price: number | null;
    price_delta_pct: number | null;
    listing_quality: {
      score: number | null;
      level: string | null;
      category_scores: Record<string, number>;
      suggestions: string[];
    } | null;
  }[];
  summary: {
    listing_count: number;
    total_views_30d: number;
    total_wishlists: number;
  };
}

interface ApiSimilarRoom {
  room: ApiRoom;
  match_score: number;
  match_reasons: string[];
}

// ============================================================
// ROOM SERVICE — real /rooms/ endpoints
// ============================================================

/** Translate UI filters into the backend's query parameters. */
function buildParams(filters: RoomFilters): Record<string, string> {
  const params: Record<string, string> = {};

  // The backend's full-text/semantic search reads `q` (see rooms/views.py).
  if (filters.query) params.q = filters.query;
  if (filters.smart) params.smart = "1";
  if (filters.area && filters.area !== "All") params.area = filters.area;
  if (filters.type && filters.type !== "All") params.room_type = filters.type.toLowerCase();
  if (filters.gender && filters.gender !== "Any")
    params.gender_preference = filters.gender.toLowerCase();
  if (filters.minPrice) params.price__gte = filters.minPrice;
  if (filters.maxPrice) params.price__lte = filters.maxPrice;
  if (filters.available === "yes") params.is_available = "true";
  if (filters.verified) params.verified = "true";
  if (filters.owner != null) params.owner = String(filters.owner);

  // Geo / map queries (Phase 7) — the backend supports bbox and a reference
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
  /**
   * GET /rooms/ with server-side filtering, sorting and search.
   * Amenities are filtered client-side (the backend has no amenities filter).
   *
   * Offline-aware (Phase 12 P1): successful PUBLIC list responses are cached
   * in IndexedDB (24h TTL); on network failure the cached result is re-filtered
   * client-side and served, and offlineCacheStatus flips to `stale` so the UI
   * can show "showing cached rooms". Nothing private is ever cached.
   */
  async getRooms(filters: RoomFilters = {}): Promise<Room[]> {
    const params = buildParams(filters);
    try {
      const { data } = await api.get<Paginated<ApiRoom>>("/rooms/", {
        params,
      });
      let rooms = data.results.map(mapRoom);

      if (filters.amenities && filters.amenities.length > 0) {
        const wanted = filters.amenities;
        rooms = rooms.filter((r) => wanted.every((a) => r.amenities.includes(a)));
      }

      void setCachedRooms(buildCacheKey(params), { rooms, ts: Date.now() });
      setOfflineCacheStatus({ stale: false, servedCount: 0, cachedTotal: 0 });
      return rooms;
    } catch (err) {
      const key = buildCacheKey(params);
      const cached = await getCachedRooms(key);
      if (cached && cacheFresh(cached.ts, ROOMS_TTL_MS)) {
        const filtered = filterCachedRooms(cached.rooms, filters);
        setOfflineCacheStatus({
          stale: true,
          servedCount: filtered.length,
          cachedTotal: cached.rooms.length,
        });
        return filtered;
      }
      throw err;
    }
  },

  /** GET /rooms/landmarks/ — public map landmark layers (universities + metro). */
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

  /** GET /rooms/:id/ — offline-aware like getRooms (public detail, 7d TTL). */
  async getRoomById(id: number): Promise<Room> {
    try {
      const { data } = await api.get<ApiRoom>(`/rooms/${id}/`);
      const room = mapRoom(data);
      void setCachedRoom(id, { room, ts: Date.now() });
      return room;
    } catch (err) {
      const cached = await getCachedRoom(id);
      if (cached && cacheFresh(cached.ts, ROOM_DETAIL_TTL_MS)) {
        setOfflineCacheStatus({ stale: true, servedCount: 1, cachedTotal: 1 });
        return cached.room;
      }
      throw err;
    }
  },

  /** PATCH /rooms/:id/ — used to apply an AI pricing suggestion. */
  async updateRoom(id: number, patch: Partial<Pick<ApiRoom, "price">>): Promise<Room> {
    const { data } = await api.patch<ApiRoom>(`/rooms/${id}/`, patch);
    return mapRoom(data);
  },

  /**
   * GET /rooms/?smart=1 — AI smart search: semantic ranking + natural-
   * language parsing (budget/area/date). Returns the rooms plus `nlParsed`,
   * what the backend understood, for "AI understood" chips.
   */
  async searchRoomsSmart(
    filters: RoomFilters = {}
  ): Promise<{ rooms: Room[]; nlParsed: NlParsed | null }> {
    const { data } = await api.get<Paginated<ApiRoom> & { nl_parsed?: NlParsed }>("/rooms/", {
      params: { ...buildParams(filters), smart: "1" },
    });
    return {
      rooms: data.results.map(mapRoom),
      nlParsed: data.nl_parsed ?? null,
    };
  },

  /**
   * GET /rooms/:id/similar-images/ — rooms whose primary photo looks like
   * this one (perceptual-hash distance, best-effort).
   */
  async getSimilarImages(roomId: number, limit = 4): Promise<SimilarImageResult[]> {
    const { data } = await api.get<(ApiRoom & { phash_distance?: number })[]>(
      `/rooms/${roomId}/similar-images/`,
      { params: { limit } }
    );
    return data.map((item) => ({
      ...mapRoom(item),
      phash_distance: item.phash_distance ?? 0,
    }));
  },

  /** GET /rooms/geocode/ — street/area/landmark autocomplete for the map search box. */
  async geocode(query: string): Promise<GeocodeSuggestion[]> {
    const { data } = await api.get<
      {
        key: string;
        label: string;
        kind: string;
        lat: number;
        lng: number;
        parent_name?: string | null;
      }[]
    >("/rooms/geocode/", { params: { q: query } });
    return data.map((s) => ({
      key: s.key,
      label: s.label,
      kind: s.kind as GeocodeSuggestion["kind"],
      lat: Number(s.lat),
      lng: Number(s.lng),
      parent_name: s.parent_name ?? null,
    }));
  },

  /**
   * GET /rooms/summary/ — aggregate room counts for the current map viewport
   * (total/available/price stats), so the map badge doesn't need the full
   * paginated list. Accepts the same geo filters as getRooms.
   */
  async getMapSummary(filters: RoomFilters = {}): Promise<MapSummary> {
    const { data } = await api.get<MapSummary>("/rooms/summary/", {
      params: buildParams(filters),
    });
    return data;
  },

  /** GET /rooms/tier-catalog/ — public paid-tier pricing/benefits. */
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

  /** POST /rooms/ — create a listing (landlord). */
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

  /** GET /rooms/insights/ → engagement stats for the landlord's listings. */
  async getInsights(): Promise<RoomInsights> {
    const { data } = await api.get<ApiRoomInsights>("/rooms/insights/");
    return {
      rooms: data.rooms.map((r) => ({
        id: r.id,
        title: r.title,
        price: r.price,
        area: r.area,
        roomType: r.room_type,
        tier: r.tier,
        verified: r.verified,
        views7d: r.views_7d,
        views30d: r.views_30d,
        viewsTotal: r.views_total,
        wishlistCount: r.wishlist_count,
        bookingRequests: r.booking_requests,
        bookingApproved: r.booking_approved,
        areaAvgPrice: r.area_avg_price,
        priceDeltaPct: r.price_delta_pct,
        listingQuality: r.listing_quality
          ? {
              score: r.listing_quality.score,
              level: r.listing_quality.level,
              categoryScores: r.listing_quality.category_scores,
              suggestions: r.listing_quality.suggestions,
            }
          : null,
      })),
      summary: {
        listingCount: data.summary.listing_count,
        totalViews30d: data.summary.total_views_30d,
        totalWishlists: data.summary.total_wishlists,
      },
    };
  },

  /** POST /rooms/bulk/ → create several listings at once (landlord). */
  async bulkCreate(
    payloads: CreateRoomPayload[]
  ): Promise<{ createdCount: number; errors: unknown[] }> {
    const body = payloads.map((payload) => ({
      title: payload.name,
      description: payload.description,
      room_type: payload.type.toLowerCase(),
      price: payload.price,
      area: payload.area,
      address: `${payload.area}, Dhaka`,
      lat: payload.lat,
      lng: payload.lng,
      amenities: payload.amenities,
      gender_preference: payload.gender.toLowerCase(),
      size_sqft: payload.size,
      is_available: payload.available,
    }));
    const { data } = await api.post<{ created_count: number; errors: unknown[] }>(
      "/rooms/bulk/",
      body
    );
    return { createdCount: data.created_count, errors: data.errors };
  },

  /** GET /recommendations/similar/<room_id>/ → content-based similar rooms. */
  async getSimilarRooms(roomId: number): Promise<SimilarRoomResult[]> {
    const { data } = await api.get<ApiSimilarRoom[]>(`/recommendations/similar/${roomId}/`);
    return data.map((r) => ({
      room: mapRoom(r.room),
      matchScore: r.match_score,
      matchReasons: r.match_reasons,
    }));
  },
};

export default roomService;
