/**
 * Map helpers — pure utilities and small React helpers used by the Map page.
 *
 * Extracted from the monolithic Map.tsx so the main component stays focused
 * on orchestration and the helpers are independently testable.
 */

import { useEffect, useState } from "react";
import { GraduationCap, MapPin, TrainFront } from "lucide-react";
import type { GeocodeSuggestion } from "../../types";
import { cn } from "../../lib/utils";

// ---------------------------------------------------------------------------
// HTML escaping
// ---------------------------------------------------------------------------

/** Escape text before it enters popup HTML (defence-in-depth — backend
 * sanitizes titles, but map popups interpolate area names too). */
export function escHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ---------------------------------------------------------------------------
// React hooks
// ---------------------------------------------------------------------------

/** Debounce a value so rapid changes (pan/zoom/type) fire only after `delayMs` ms. */
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(t);
  }, [value, delayMs]);
  return debounced;
}

// ---------------------------------------------------------------------------
// Clipboard
// ---------------------------------------------------------------------------

/**
 * Clipboard fallback for non-secure contexts (plain http) where
 * navigator.clipboard is unavailable — a temporary textarea + execCommand.
 */
export function fallbackCopy(text: string, onDone: () => void) {
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
    onDone();
  } catch {
    // Copy failed (e.g. blocked) — surface the URL in the address bar instead.
    window.prompt("Copy this map link:", text);
  }
}

// ---------------------------------------------------------------------------
// Tiny presentational helpers
// ---------------------------------------------------------------------------

export function SuggestionIcon({ kind }: { kind: GeocodeSuggestion["kind"] }) {
  const cls = "size-4 shrink-0";
  switch (kind) {
    case "university":
      return <GraduationCap className={cn(cls, "text-violet-600 dark:text-violet-400")} />;
    case "metro":
      return <TrainFront className={cn(cls, "text-teal-600 dark:text-teal-400")} />;
    case "area":
      return <MapPin className={cn(cls, "text-orange-600 dark:text-orange-400")} />;
    default:
      return <MapPin className={cn(cls, "text-blue-600 dark:text-blue-400")} />;
  }
}
