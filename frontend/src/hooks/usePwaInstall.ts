import { useCallback, useEffect, useState } from "react";
import {
  installDismissed,
  isStandalone,
  markInstallDismissed,
  type BeforeInstallPromptEvent,
} from "../lib/pwa";

/**
 * Browser install-prompt lifecycle.
 *
 * - Captures `beforeinstallprompt` (prevented by default so WE choose when to
 *   show the native prompt — never a surprise popup on first visit).
 * - Tracks `appinstalled` and `(display-mode: standalone)` so the CTA
 *   disappears once the app is actually installed.
 * - Honors a one-week dismissal cooldown (polite, non-nagging).
 */
export function usePwaInstall() {
  const [deferredPrompt, setDeferredPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [installed, setInstalled] = useState<boolean>(() => isStandalone());

  useEffect(() => {
    if (!("onbeforeinstallprompt" in window)) return;

    const onPrompt = (e: Event) => {
      e.preventDefault();
      // If the user already dismissed recently, don't re-arm the prompt.
      if (installDismissed()) return;
      setDeferredPrompt(e as BeforeInstallPromptEvent);
    };
    const onInstalled = () => {
      setInstalled(true);
      setDeferredPrompt(null);
    };
    const onDisplayMode = (e: MediaQueryListEvent) => {
      if (e.matches) setInstalled(true);
    };

    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("appinstalled", onInstalled);
    const mql = window.matchMedia("(display-mode: standalone)");
    mql.addEventListener("change", onDisplayMode);

    return () => {
      window.removeEventListener("beforeinstallprompt", onPrompt);
      window.removeEventListener("appinstalled", onInstalled);
      mql.removeEventListener("change", onDisplayMode);
    };
  }, []);

  /** Ask the browser for the native install prompt. Returns true if accepted. */
  const promptInstall = useCallback(async (): Promise<boolean> => {
    if (!deferredPrompt) return false;
    try {
      await deferredPrompt.prompt();
      const choice = await deferredPrompt.userChoice;
      if (choice.outcome === "accepted") {
        setInstalled(true);
        setDeferredPrompt(null);
        return true;
      }
      // Dismissed — respect the user and cool off for a week.
      markInstallDismissed();
      setDeferredPrompt(null);
      return false;
    } catch {
      return false;
    }
  }, [deferredPrompt]);

  const dismiss = useCallback(() => {
    markInstallDismissed();
    setDeferredPrompt(null);
  }, []);

  return { canInstall: deferredPrompt !== null && !installed, installed, promptInstall, dismiss };
}
