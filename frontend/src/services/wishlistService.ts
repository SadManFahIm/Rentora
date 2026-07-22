import { api } from "./api";
import { mapRoom, type ApiRoom, type Paginated } from "./mappers";
import type { Room } from "../types";

// ============================================================
// WISHLIST SERVICE — real /wishlist/ endpoints
// ============================================================

interface ApiWishlistEntry {
  id: number;
  room: ApiRoom;
  created_at: string;
}

export interface WishlistToggleResult {
  status: "added" | "removed";
  wishlisted: boolean;
}

export const wishlistService = {
  /** GET /wishlist/ → the user's saved rooms. */
  async getWishlist(): Promise<Room[]> {
    const { data } = await api.get<Paginated<ApiWishlistEntry>>("/wishlist/");
    return data.results.map((entry) => mapRoom(entry.room));
  },

  /** GET /wishlist/ → just the saved room ids (for the store). */
  async getWishlistIds(): Promise<number[]> {
    const { data } = await api.get<Paginated<ApiWishlistEntry>>("/wishlist/");
    return data.results.map((entry) => entry.room.id);
  },

  /** POST /wishlist/toggle/ → add or remove a room, returns the new state. */
  async toggleWishlist(roomId: number): Promise<WishlistToggleResult> {
    const { data } = await api.post<WishlistToggleResult>("/wishlist/toggle/", {
      room_id: roomId,
    });
    return data;
  },
};

export default wishlistService;
