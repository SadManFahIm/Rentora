/**
 * PWA helpers — installability, standalone detection, update/offline policy.
 *
 * Kept dependency-free so the browser-facing hooks stay thin and the pure
 * policy logic (dismissal cooldowns, manifest shape) is unit-testable.
 */

/** The Chrome `beforeinstallprompt` event — not part of the TS DOM lib yet. */
export interface BeforeInstallPromptEvent extends Event {
  readonly platforms: string[];
  readonly userChoice: Promise<{ outcome: "accepted" | "dismissed"; platform: string }>;
  prompt(): Promise<void>;
}

export const PWA_DISMISS_KEY = "rentora:pwa:install-dismissed-at";
export const PWA_UPDATE_DISMISS_KEY = "rentora:pwa:update-dismissed-at";

/** How long a dismissed install CTA stays hidden (7 days). */
export const INSTALL_DISMISS_COOLDOWN_MS = 7 * 24 * 60 * 60 * 1000;
/** How long a dismissed "new version" banner stays hidden (24h). */
export const UPDATE_DISMISS_COOLDOWN_MS = 24 * 60 * 60 * 1000;

/** Manifest shortcuts — must mirror the real React Router routes. */
export const PWA_SHORTCUTS = [
  { name: "Search Rooms", short_name: "Search", url: "/rooms" },
  { name: "Explore Map", short_name: "Map", url: "/map" },
  { name: "Post Listing", short_name: "List", url: "/dashboard?tab=listings" },
] as const;

/**
 * True when the app is running as an installed PWA (standalone, or on iOS
 * home-screen fullscreen). Pass matchMedia for testability.
 */
export function isStandalone(
  matchMediaFn: (query: string) => { matches: boolean } = window.matchMedia.bind(window)
): boolean {
  const mql = matchMediaFn("(display-mode: standalone)");
  return mql.matches;
}

/** LocalStorage-safe timestamp read (returns null on any failure). */
function readTimestamp(key: string): number | null {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const value = Number(raw);
    return Number.isFinite(value) ? value : null;
  } catch {
    return null;
  }
}

/** True when the user dismissed the install CTA within the cooldown window. */
export function installDismissed(now: number = Date.now()): boolean {
  const ts = readTimestamp(PWA_DISMISS_KEY);
  return ts !== null && now - ts < INSTALL_DISMISS_COOLDOWN_MS;
}

/** Record an install-CTA dismissal (polite: one dismissal hides it for a week). */
export function markInstallDismissed(now: number = Date.now()): void {
  try {
    localStorage.setItem(PWA_DISMISS_KEY, String(now));
  } catch {
    // storage unavailable (private mode) — the prompt simply shows again
  }
}

/** True when the update banner is still within its dismissal cooldown. */
export function updateDismissed(now: number = Date.now()): boolean {
  const ts = readTimestamp(PWA_UPDATE_DISMISS_KEY);
  return ts !== null && now - ts < UPDATE_DISMISS_COOLDOWN_MS;
}

/** Record an update-banner dismissal. */
export function markUpdateDismissed(now: number = Date.now()): void {
  try {
    localStorage.setItem(PWA_UPDATE_DISMISS_KEY, String(now));
  } catch {
    // ignore
  }
}

/** Fetch the manifest from the app's base path. */
export async function fetchManifest(baseUrl = "/"): Promise<Record<string, unknown>> {
  const res = await fetch(`${baseUrl}manifest.webmanifest`);
  if (!res.ok) throw new Error(`manifest fetch failed: ${res.status}`);
  return (await res.json()) as Record<string, unknown>;
}

/**
 * Validate the essential installability fields of a parsed manifest.
 * Returns a list of problems (empty = valid). Used by tests and CI.
 */
export function validateManifest(manifest: Record<string, unknown>): string[] {
  const problems: string[] = [];
  const requiredStrings = [
    "name",
    "short_name",
    "start_url",
    "scope",
    "display",
    "theme_color",
    "background_color",
  ] as const;
  for (const key of requiredStrings) {
    if (typeof manifest[key] !== "string" || !manifest[key])
      problems.push(`missing or non-string "${key}"`);
  }
  const icons = Array.isArray(manifest.icons) ? manifest.icons : [];
  if (!icons.some((i) => (i as { sizes?: string }).sizes === "192x192"))
    problems.push("no 192x192 icon");
  if (!icons.some((i) => (i as { sizes?: string }).sizes === "512x512"))
    problems.push("no 512x512 icon");
  if (!icons.some((i) => (i as { purpose?: string }).purpose === "maskable"))
    problems.push("no maskable icon");
  if (manifest.display !== "standalone") problems.push(`display should be "standalone"`);
  return problems;
}
