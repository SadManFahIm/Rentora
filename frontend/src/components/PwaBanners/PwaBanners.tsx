import { usePwaUpdate } from "../../hooks/usePwaUpdate";
import { useOnline } from "../../hooks/useOnline";
import { Button } from "../ui/button";

/**
 * Global PWA banners rendered above everything:
 * - offline notice (graceful — loaded UI stays visible, no fake data),
 * - "new version available" with Refresh / Later.
 */
export default function PwaBanners() {
  const online = useOnline();
  const { updateAvailable, refresh, dismiss } = usePwaUpdate();

  return (
    <>
      {!online && (
        <div
          role="status"
          className="sticky top-16 z-[120] border-b border-amber-200 bg-amber-50 px-4 py-2 text-center text-sm font-medium text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200"
          style={{ paddingTop: "max(0.5rem, env(safe-area-inset-top))" }}
        >
          📡 You're offline — some Rentora features may be unavailable. Reconnecting…
        </div>
      )}

      {updateAvailable && (
        <div
          role="alert"
          className="fixed inset-x-0 bottom-4 z-[130] mx-auto flex max-w-md items-center gap-3 rounded-xl border border-orange-200 bg-white px-4 py-3 shadow-lg dark:border-orange-900 dark:bg-gray-900"
          style={{ marginBottom: "env(safe-area-inset-bottom)" }}
        >
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-foreground">
              A new version of Rentora is available
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Refresh to get the latest updates.
            </p>
          </div>
          <Button size="sm" onClick={refresh}>
            Refresh
          </Button>
          <button
            type="button"
            onClick={dismiss}
            className="text-xs font-medium text-gray-500 underline-offset-2 hover:underline dark:text-gray-400"
          >
            Later
          </button>
        </div>
      )}
    </>
  );
}
