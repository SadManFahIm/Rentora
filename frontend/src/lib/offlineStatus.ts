/**
 * Offline-cache status — lets the UI show "showing cached rooms (offline)"
 * without threading a flag through every query. Set by the room service when
 * it serves from the IndexedDB cache; read via useOfflineCacheStatus.
 */

export interface OfflineCacheStatus {
  /** True when the last served result came from the offline cache. */
  stale: boolean;
  /** Number of rooms served from cache after client-side filtering. */
  servedCount: number;
  /** Total rooms available in the cache for the current query. */
  cachedTotal: number;
}

type Listener = (status: OfflineCacheStatus) => void;

let current: OfflineCacheStatus = { stale: false, servedCount: 0, cachedTotal: 0 };
const listeners = new Set<Listener>();

export function setOfflineCacheStatus(status: OfflineCacheStatus): void {
  current = status;
  for (const l of listeners) l(current);
}

export function getOfflineCacheStatus(): OfflineCacheStatus {
  return current;
}

export function subscribeOfflineCacheStatus(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
