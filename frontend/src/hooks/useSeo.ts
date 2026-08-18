import { useEffect } from "react";

/**
 * Lightweight SPA SEO hook (Phase 13 — Reach).
 *
 * Keeps the document title and meta description in sync with the current
 * page, so area landing pages at `/rooms/<slug>` show search-friendly titles
 * and descriptions. Honest scope: Rentora is a client-rendered SPA, so this
 * updates the in-page metadata after mount — true server-rendered SEO would
 * come from pre-rendering (see docs/phase-13-reach.md).
 *
 * Saves the previous title/description and restores them on unmount so the
 * shared Home/Rooms pages keep their defaults when navigating away.
 */

const BASE_TITLE = "Rentora — AI-Powered Room Rental in Bangladesh";

export function useSeo(title: string, description?: string): void {
  useEffect(() => {
    const prevTitle = document.title;
    document.title = title || BASE_TITLE;

    let meta: HTMLMetaElement | null = document.querySelector('meta[name="description"]');
    const prevDescription = meta?.getAttribute("content") ?? "";
    if (description && !meta) {
      meta = document.createElement("meta");
      meta.name = "description";
      document.head.appendChild(meta);
    }
    meta?.setAttribute("content", description ?? "");

    return () => {
      document.title = prevTitle;
      if (description) meta?.setAttribute("content", prevDescription);
    };
  }, [title, description]);
}
