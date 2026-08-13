import { useState } from "react";
import { Download, X } from "lucide-react";
import { usePwaInstall } from "../../hooks/usePwaInstall";
import { isStandalone } from "../../lib/pwa";
import { Button } from "../ui/button";

const IOS_HINT_KEY = "rentora:pwa:ios-hint-dismissed";

function isIosSafari(): boolean {
  if (typeof navigator === "undefined") return false;
  const ua = navigator.userAgent;
  const isIos = /iphone|ipad|ipod/i.test(ua);
  const isSafari = /safari/i.test(ua) && !/crios|fxios|edgios|opios/i.test(ua);
  return isIos && isSafari;
}

/**
 * Install Rentora CTA.
 *
 * - Chromium (Chrome/Edge): subtle navbar button that fires the browser's
 *   NATIVE install prompt — only when a prompt is offered, never a fake popup.
 * - iOS Safari: no install-prompt API exists, so we show a one-time, politely
 *   dismissible "Add to Home Screen" hint instead.
 *
 * Everything disappears once the app is installed (standalone) or dismissed.
 */
export default function PwaInstallPrompt() {
  const { canInstall, installed, promptInstall, dismiss } = usePwaInstall();
  const [iosHintDismissed, setIosHintDismissed] = useState<boolean>(() => {
    try {
      return localStorage.getItem(IOS_HINT_KEY) === "1";
    } catch {
      return false;
    }
  });

  const iosHintVisible = isIosSafari() && !installed && !isStandalone() && !iosHintDismissed;

  if (iosHintVisible) {
    return (
      <div className="fixed inset-x-4 bottom-4 z-[130] mx-auto flex max-w-md items-start gap-3 rounded-xl border border-orange-200 bg-white p-4 shadow-lg dark:border-orange-900 dark:bg-gray-900">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-foreground">Install Rentora on your phone</p>
          <p className="mt-0.5 text-xs leading-relaxed text-gray-500 dark:text-gray-400">
            Tap the <span className="font-medium text-gray-700 dark:text-gray-300">Share</span>{" "}
            button in Safari, then choose{" "}
            <span className="font-medium text-gray-700 dark:text-gray-300">Add to Home Screen</span>{" "}
            — Rentora opens like a native app.
          </p>
        </div>
        <button
          type="button"
          aria-label="Dismiss install hint"
          onClick={() => {
            setIosHintDismissed(true);
            try {
              localStorage.setItem(IOS_HINT_KEY, "1");
            } catch {
              // ignore
            }
          }}
          className="text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300"
        >
          <X className="size-4" aria-hidden />
        </button>
      </div>
    );
  }

  if (!canInstall) return null;

  return (
    <Button
      variant="outline"
      size="sm"
      onClick={() => {
        void promptInstall().then((accepted) => {
          if (!accepted) dismiss();
        });
      }}
      className="hidden items-center gap-1.5 md:inline-flex"
      aria-label="Install Rentora as an app"
    >
      <Download className="h-4 w-4" aria-hidden />
      <span>Install app</span>
    </Button>
  );
}
