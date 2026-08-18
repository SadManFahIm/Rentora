import { create } from "zustand";

export interface ListingContext {
  id: number;
  title: string;
  price?: number;
}

export type AiToolRequest = "negotiate" | "advisor" | "agreement" | null;

/**
 * Cross-component channel for the Copilot (Tier 3 RAG listing mode + Tier 4
 * AI tools).
 *
 * The floating CopilotWidget lives in the Layout shell; pages like the
 * RoomModal need to open it *grounded on a specific listing*. The widget
 * subscribes to `listingContext` and opens itself with a listing-mode
 * banner whenever it's set; `clearListingContext` resets back to plain
 * search mode (also triggered by the widget's own reset).
 *
 * `aiToolRequest` is a one-shot channel: a page (e.g. RoomModal's "Draft
 * negotiation" button) asks the widget to open directly on an AI tool tab;
 * the widget consumes it on render and clears it.
 */
interface CopilotStore {
  listingContext: ListingContext | null;
  openWithListing: (listing: ListingContext) => void;
  clearListingContext: () => void;
  aiToolRequest: AiToolRequest;
  requestAiTool: (tool: Exclude<AiToolRequest, null>) => void;
  consumeAiTool: () => void;
}

export const useCopilotStore = create<CopilotStore>((set) => ({
  listingContext: null,
  openWithListing: (listing) => set({ listingContext: listing }),
  clearListingContext: () => set({ listingContext: null }),
  aiToolRequest: null,
  requestAiTool: (tool) => set({ aiToolRequest: tool }),
  consumeAiTool: () => set({ aiToolRequest: null }),
}));
