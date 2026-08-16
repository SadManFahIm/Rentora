import { useCallback, useRef, useState } from "react";
import { toast } from "sonner";
import { sendCopilotMessage, type CopilotChatMessage } from "../services/copilotService";
import { getApiErrorMessage } from "../services/errors";
import { useCopilotStore } from "../stores/copilotStore";

let messageSeq = 0;
const nextId = () => `copilot-${Date.now()}-${messageSeq++}`;

/**
 * Stateful Copilot conversation: message list, in-flight flag, and `send`
 * which threads the session id through so follow-ups keep context.
 *
 * Tier 3 listing mode: when a listing context is active (set via
 * `openWithListing` in the shared store) every turn is sent with the
 * listing_id so the backend answers strictly over that listing's facts.
 */
export function useCopilot() {
  const [messages, setMessages] = useState<CopilotChatMessage[]>([]);
  const [isSending, setIsSending] = useState(false);
  const [isOpen, setIsOpen] = useState(false);
  const [listingMode, setListingMode] = useState(false);
  const sessionRef = useRef<string | null>(null);
  const listingIdRef = useRef<number | null>(null);

  const send = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || isSending) return;

      setMessages((prev) => [...prev, { id: nextId(), role: "user", text: trimmed }]);
      setIsSending(true);
      try {
        const res = await sendCopilotMessage(trimmed, sessionRef.current, listingIdRef.current);
        sessionRef.current = res.session_id;
        if (res.mode === "listing") {
          setListingMode(true);
        }
        setMessages((prev) => [
          ...prev,
          {
            id: nextId(),
            role: "assistant",
            text: res.message,
            listings: res.listings,
            suggestions: res.suggestions,
            intent: res.intent,
          },
        ]);
      } catch (error) {
        toast.error(getApiErrorMessage(error, "Copilot is busy — try again."));
        setMessages((prev) => [
          ...prev,
          {
            id: nextId(),
            role: "assistant",
            text: "Sorry, I couldn't reach the search engine. Please try again in a moment.",
          },
        ]);
      } finally {
        setIsSending(false);
      }
    },
    [isSending]
  );

  /**
   * Seed a listing-grounded conversation (called by the widget when the
   * shared store's `listingContext` changes). Every subsequent turn is sent
   * with the listing_id so answers come from that listing's facts only.
   */
  const openWithListing = useCallback((listing: { id: number; title: string }) => {
    listingIdRef.current = listing.id;
    sessionRef.current = null;
    setListingMode(true);
    setMessages([
      {
        id: nextId(),
        role: "assistant",
        text: `I'm looking at “${listing.title}” — ask me anything about it (price, amenities, area, verification) and I'll answer from the listing's facts only.`,
        suggestions: ["দাম কত?", "কি সুবিধা আছে?", "কোথায় অবস্থিত?", "ভেরিফাইড কি?"],
      },
    ]);
    setIsOpen(true);
  }, []);

  const reset = useCallback(() => {
    sessionRef.current = null;
    listingIdRef.current = null;
    setMessages([]);
    setListingMode(false);
    useCopilotStore.getState().clearListingContext();
  }, []);

  return { messages, isSending, isOpen, setIsOpen, send, reset, openWithListing, listingMode };
}
