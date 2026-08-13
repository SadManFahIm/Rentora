import { useCallback, useEffect, useState } from "react";
import { markUpdateDismissed, updateDismissed } from "../lib/pwa";

/**
 * "A new version of Rentora is available" detection.
 *
 * The service worker `skipWaiting()`s and `clients.claim()`s so a freshly
 * deployed worker takes over promptly (push stays current). When it does, the
 * page's controller changes — that transition is the signal that a new build
 * is live, and a refresh will load it. We ignore the very first controller
 * (the initial install) so the banner never fires on first visit.
 */
export function usePwaUpdate() {
  const [updateAvailable, setUpdateAvailable] = useState(false);

  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;

    // A controllerchange AFTER the first control means a newer build took over.
    let controlled = Boolean(navigator.serviceWorker.controller);
    const onChange = () => {
      if (!controlled) {
        controlled = true;
        return;
      }
      if (!updateDismissed()) setUpdateAvailable(true);
    };
    navigator.serviceWorker.addEventListener("controllerchange", onChange);
    return () => navigator.serviceWorker.removeEventListener("controllerchange", onChange);
  }, []);

  const refresh = useCallback(() => {
    window.location.reload();
  }, []);

  const dismiss = useCallback(() => {
    markUpdateDismissed();
    setUpdateAvailable(false);
  }, []);

  return { updateAvailable, refresh, dismiss };
}
