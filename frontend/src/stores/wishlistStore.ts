import { create } from "zustand";
import { persist } from "zustand/middleware";

// ============================================================
// WISHLIST STORE — saved room ids (client-side, persisted)
// ============================================================

interface WishlistState {
  wishlist: number[];
  toggleWishlist: (roomId: number) => void;
  isWishlisted: (roomId: number) => boolean;
  clearWishlist: () => void;
}

export const useWishlistStore = create<WishlistState>()(
  persist(
    (set, get) => ({
      wishlist: [],
      toggleWishlist: (roomId) =>
        set((s) => ({
          wishlist: s.wishlist.includes(roomId)
            ? s.wishlist.filter((id) => id !== roomId)
            : [...s.wishlist, roomId],
        })),
      isWishlisted: (roomId) => get().wishlist.includes(roomId),
      clearWishlist: () => set({ wishlist: [] }),
    }),
    {
      name: "rentora-wishlist",
    }
  )
);
