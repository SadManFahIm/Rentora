import { useEffect } from "react";
import { registerBackgroundSync, replayQueue } from "../lib/backgroundSync";
import { requestPeriodicRefresh } from "../lib/periodicSync";
import { isStandalone } from "../lib/pwa";
import { roomService } from "../services/roomService";

/**
 * App-level background-sync wiring. Mounted once (inside App).
 *
 * Replays the offline action queue when the connection returns, whether that
 * arrives as a browser Background Sync event (via the service worker), an
 * `online` event, or a `visibilitychange` back to a visible tab.
 */
export function useBackgroundSync(): void {
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;

    // Ask the SW to register a one-shot sync for the replay tag, and listen
    // for the SW's "please replay now" message.
    navigator.serviceWorker.ready.then((reg) => {
      void registerBackgroundSync(reg);
      // Periodic Background Sync (Chromium + installed PWA only): keep the
      // PUBLIC cached listings fresh daily. No-op elsewhere.
      if (isStandalone()) void requestPeriodicRefresh(reg);
    });
    navigator.serviceWorker.addEventListener("message", (event) => {
      if (event.data?.type === "rentora-replay") void replayQueue();
      // SW ran a periodic refresh — re-fetch the default public list so the
      // offline cache holds fresh data (writes straight into IndexedDB).
      if (event.data?.type === "rentora-periodic-refresh") {
        void roomService.getRooms({}).catch(() => undefined);
      }
    });

    // Universal fallback — online event and returning to a visible tab.
    const onOnline = () => void replayQueue();
    const onVisible = () => {
      if (document.visibilityState === "visible" && navigator.onLine) void replayQueue();
    };
    window.addEventListener("online", onOnline);
    document.addEventListener("visibilitychange", onVisible);

    return () => {
      window.removeEventListener("online", onOnline);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);
}
