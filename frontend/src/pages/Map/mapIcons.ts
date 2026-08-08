import L from "leaflet";

/** Compact price label for a marker, e.g. 8000 -> "৳8k", 22000 -> "৳22k". */
function compactPrice(price: number): string {
  if (price >= 1000) return `৳${Math.round(price / 1000)}k`;
  return `৳${price}`;
}

/**
 * A price-pill map marker. Built as a Leaflet `divIcon` so it can be styled
 * with the app's Tailwind classes (the global stylesheet is already loaded on
 * the page). The `active` variant is the highlight used for list↔map hover sync.
 */
export function priceMarkerIcon(price: number, active: boolean): L.DivIcon {
  const base =
    "flex h-full w-full items-center justify-center rounded-full border text-xs font-bold shadow-md transition-colors";
  const variant = active
    ? "bg-orange-600 text-white border-orange-700"
    : "bg-white text-gray-900 border-gray-300 dark:bg-gray-900 dark:text-gray-100 dark:border-gray-700";
  return L.divIcon({
    className: "rentora-price-marker",
    html: `<span class="${base} ${variant}">${compactPrice(price)}</span>`,
    iconSize: [52, 26],
    iconAnchor: [26, 13],
    popupAnchor: [0, -16],
  });
}
