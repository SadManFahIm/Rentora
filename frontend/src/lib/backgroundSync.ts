import { api } from "../services/api";
import { clearQueue, enqueueAction, listQueue, type OfflineAction } from "./offlineDb";

/**
 * Background sync (Phase 12 P1) — replay user actions made while offline.
 *
 * Queue → replay pipeline:
 *   1. A mutation made while offline is queued in IndexedDB (`enqueueAction`).
 *   2. Reconnect triggers a replay — via the browser's Background Sync API
 *      (`registration.sync`), or the `online` / `visibilitychange` events as a
 *      universal fallback.
 *   3. Each queued action is replayed exactly once; failures stay queued for
 *      the next attempt. Successful replays are cleared.
 *
 * Only idempotent-ish public/user actions are queued (wishlist toggle,
 * saved-search check) — never auth or payment operations.
 */

export const SYNC_TAG = "rentora-replay";

export { enqueueAction };

/** Register a one-shot background sync when the browser supports it. */
interface SyncCapableRegistration extends ServiceWorkerRegistration {
  sync?: { register(tag: string): Promise<void> };
}

export async function registerBackgroundSync(reg: ServiceWorkerRegistration): Promise<boolean> {
  const sync = (reg as SyncCapableRegistration).sync;
  if (sync) {
    try {
      await sync.register(SYNC_TAG);
      return true;
    } catch {
      return false;
    }
  }
  return false;
}

/** Replay every queued offline action. Returns the number replayed. */
export async function replayQueue(): Promise<number> {
  const actions = await listQueue();
  if (!actions || actions.length === 0) return 0;

  let replayed = 0;
  const remaining: OfflineAction[] = [];
  for (const action of actions) {
    try {
      if (action.type === "wishlist-toggle") {
        await api.post("/wishlist/toggle/", { room_id: action.payload.roomId });
      } else if (action.type === "saved-search-check") {
        await api.post(`/saved-searches/${action.payload.id}/check/`);
      }
      replayed += 1;
    } catch {
      remaining.push(action); // retry next time — never drop silently
    }
  }

  if (remaining.length === 0) {
    await clearQueue();
  } else {
    // Re-store the ones that failed (clear + re-add preserves ordering).
    await clearQueue();
    for (const action of remaining) await enqueueAction(action);
  }
  return replayed;
}
