/**
 * Periodic Background Sync (Phase 12 P1, feasible subset).
 *
 * Status (research, 2026):
 *   - `registration.periodicSync` — Chromium only (Chrome/Edge 80+, Android),
 *     requires an INSTALLED PWA + the `periodic-background-sync` permission;
 *     the browser schedules the runs (minInterval is a hint, site-engagement
 *     gated). Safari/Firefox: unsupported — we degrade silently.
 *   - Notification Triggers API — NOT shipped in any browser (abandoned in
 *     Chromium); documented as future scope in docs/PWA.md.
 *
 * What we do with it: when installed, register a daily `rentora-refresh` task
 * that tells the app to refresh the PUBLIC cached listings so the offline
 * cache never rots. No-op everywhere else.
 */

export const PERIODIC_REFRESH_TAG = "rentora-refresh";
export const MIN_INTERVAL_MS = 24 * 60 * 60 * 1000; // hint only — browser decides

export type PeriodicSyncStatus = "registered" | "unsupported" | "denied" | "already" | "error";

interface PeriodicSyncCapableRegistration extends ServiceWorkerRegistration {
  periodicSync?: {
    register(tag: string, options: { minInterval: number }): Promise<void>;
    getTags(): Promise<string[]>;
  };
}

/** Register the daily public-cache refresh. Best-effort, never throws. */
export async function requestPeriodicRefresh(
  reg: ServiceWorkerRegistration
): Promise<PeriodicSyncStatus> {
  try {
    const periodicSync = (reg as PeriodicSyncCapableRegistration).periodicSync;
    if (!periodicSync) return "unsupported";

    // The permission exists only in Chromium; the query throws elsewhere.
    let state: PermissionState = "denied";
    try {
      const status = await navigator.permissions.query({
        // @ts-expect-error — not in the TS DOM lib yet (Chromium-only API)
        name: "periodic-background-sync",
      });
      state = status.state;
    } catch {
      return "unsupported";
    }
    if (state !== "granted") return "denied";

    const existing = await periodicSync.getTags();
    if (existing.includes(PERIODIC_REFRESH_TAG)) return "already";

    await periodicSync.register(PERIODIC_REFRESH_TAG, {
      minInterval: MIN_INTERVAL_MS,
    });
    return "registered";
  } catch {
    return "error";
  }
}
