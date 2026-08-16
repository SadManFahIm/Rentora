import { create } from "zustand";

export interface ListingContext {
  id: number;
  title: string;
}

/**
 * Cross-component channel for the Copilot (Tier 3 RAG listing mode).
 *
 * The floating CopilotWidget lives in the Layout shell; pages like the
 * RoomModal need to open it *grounded on a specific listing*. The widget
 * subscribes to `listingContext` and opens itself with a listing-mode
 * banner whenever it's set; `clearListingContext` resets back to plain
 * search mode (also triggered by the widget's own reset).
 */
interface CopilotStore {
  listingContext: ListingContext | null;
  openWithListing: (listing: ListingContext) => void;
  clearListingContext: () => void;
}

export const useCopilotStore = create<CopilotStore>((set) => ({
  listingContext: null,
  openWithListing: (listing) => set({ listingContext: listing }),
  clearListingContext: () => set({ listingContext: null }),
}));
