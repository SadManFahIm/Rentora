/**
 * Share helpers (Phase 13 — WhatsApp reach).
 *
 * A listing can be shared to WhatsApp two ways:
 *  - a rich, AI-grounded summary prefetched from
 *    `GET /api/v1/copilot/share-summary/<id>/` (deterministic, public fields
 *    only — never invented), or
 *  - a local fallback built from the same public fields when the request
 *    fails or the backend isn't reachable.
 *
 * The share link always opens `https://wa.me/?text=...` so it works on any
 * device (Bangladesh's primary messenger) without a custom scheme.
 */

/** Compose a `https://wa.me/?text=` URL with percent-encoded body. */
export function whatsappShareUrl(text: string): string {
  return `https://wa.me/?text=${encodeURIComponent(text)}`;
}

/** Deterministic local fallback summary (mirrors backend listing_share_summary). */
export function buildListingShareText(room: {
  id: number;
  name: string;
  price: number;
  area: string;
  type?: string;
  amenities?: string[];
  verified?: boolean;
}): string {
  const parts = [`${room.name} — ${room.area}`, `৳${room.price.toLocaleString()}/month`];
  if (room.type) parts.push(room.type);
  if (room.amenities?.length) parts.push(`✓ ${room.amenities.slice(0, 4).join(", ")}`);
  if (room.verified) parts.push("✓ identity-verified listing");
  return parts.join(" · ");
}

/** The full share body: summary + the public link to the room. */
export function buildWhatsAppShareText(
  summary: string,
  room: { id: number; name: string; area: string }
): string {
  return `${summary}\n\nCheck it on Rentora — ${room.area} room for rent: ${window.location.origin}/rooms/${room.area.toLowerCase()}?room=${room.id}`;
}
