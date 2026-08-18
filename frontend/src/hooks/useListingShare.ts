import { useCallback, useState } from "react";
import { getListingShareSummary } from "../services/copilotService";
import { buildListingShareText, buildWhatsAppShareText, whatsappShareUrl } from "../lib/share";

/**
 * WhatsApp share hook (Phase 13 — Reach).
 *
 * Tries the AI-grounded summary first (`GET /copilot/share-summary/<id>/`);
 * if that fails (backend offline, 404, …) it falls back to a deterministic
 * summary built from the same public listing fields. The recipient always
 * gets real facts — never invented claims.
 */
export function useListingShare() {
  const [sharingId, setSharingId] = useState<number | null>(null);

  const share = useCallback(
    async (room: {
      id: number;
      name: string;
      price: number;
      area: string;
      type?: string;
      amenities?: string[];
      verified?: boolean;
    }) => {
      setSharingId(room.id);
      try {
        let summary: string;
        try {
          const data = await getListingShareSummary(room.id);
          summary = data.summary;
        } catch {
          summary = buildListingShareText(room);
        }
        const text = buildWhatsAppShareText(summary, room);
        window.open(whatsappShareUrl(text), "_blank", "noopener,noreferrer");
      } finally {
        setSharingId(null);
      }
    },
    []
  );

  return { share, sharingId };
}
