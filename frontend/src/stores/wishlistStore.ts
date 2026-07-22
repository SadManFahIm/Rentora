import { create } from "zustand";
import { persist } from "zustand/middleware";
import { toast } from "sonner";
import { isAuthenticated } from "../services/api";
import { wishlistService } from "../services/wishlistService";
import { getApiErrorMessage } from "../services/errors";

// ============================================================
// WISHLIST STORE
// Saved room ids, persisted locally and synced with the backend
// while the user is authenticated. Toggles update optimistically
// and roll back on failure.
// ============================================================

interface WishlistState {
  wishlist: number[];
  isWishlisted: (roomId: number) => boolean;
  /** Toggle a room: optimistic local update + backend sync when logged in. */
  toggleWishlist: (roomId: number) => Promise<void>;
  /** Replace the local list with the server's (called on login/bootstrap). */
  syncFromServer: () => Promise<void>;
  setWishlist: (ids: number[]) => void;
  clearWishlist: () => void;
}

export const useWishlistStore = create<WishlistState>()(
  persist(
    (set, get) => ({
      wishlist: [],

      isWishlisted: (roomId) => get().wishlist.includes(roomId),

      toggleWishlist: async (roomId) => {
        const wasWishlisted = get().wishlist.includes(roomId);

        // Optimistic update.
        set((s) => ({
          wishlist: wasWishlisted
            ? s.wishlist.filter((id) => id !== roomId)
            : [...s.wishlist, roomId],
        }));

        if (!isAuthenticated()) return; // guest: local-only

        try {
          await wishlistService.toggleWishlist(roomId);
        } catch (error) {
          // Roll back on failure.
          set((s) => ({
            wishlist: wasWishlisted
              ? [...s.wishlist, roomId]
              : s.wishlist.filter((id) => id !== roomId),
          }));
          toast.error(getApiErrorMessage(error, "Could not update wishlist."));
        }
      },

      syncFromServer: async () => {
        if (!isAuthenticated()) return;
        try {
          const ids = await wishlistService.getWishlistIds();
          set({ wishlist: ids });
        } catch {
          // Non-fatal: keep whatever is persisted locally.
        }
      },

      setWishlist: (ids) => set({ wishlist: ids }),
      clearWishlist: () => set({ wishlist: [] }),
    }),
    {
      name: "rentora-wishlist",
      partialize: (state) => ({ wishlist: state.wishlist }),
    }
  )
);
