import type { Room, RoomFilters } from "../types";

/**
 * Offline cache (Phase 12 P1).
 *
 * POLICY — public data ONLY:
 *   - stores room LIST results (per query) and room DETAILS (per id), which any
 *     visitor can see; used as a network-first fallback when offline.
 *   - NEVER stores auth responses, admin/fraud evidence, payment payloads,
 *     landlord/tenant private data, or personalized API responses.
 *
 * The IndexedDB layer degrades silently (returns null / no-ops) when the API
 * is unavailable (private mode, old browsers) — offline caching is a
 * progressive enhancement, never a blocker.
 */

export const ROOMS_TTL_MS = 24 * 60 * 60 * 1000; // list results: 24h
export const ROOM_DETAIL_TTL_MS = 7 * 24 * 60 * 60 * 1000; // detail: 7d
const DB_NAME = "rentora-offline";
const DB_VERSION = 1;
const STORE_ROOMS = "rooms"; // key: cacheKey, value: { rooms, nlParsed, ts }
const STORE_ROOM = "room"; // key: String(id), value: { room, ts }
const STORE_QUEUE = "queue"; // key: auto, value: { type, payload, ts }

export interface CachedRoomList {
  rooms: Room[];
  nlParsed?: unknown;
  ts: number;
}

export interface CachedRoom {
  room: Room;
  ts: number;
}

export type OfflineAction =
  | { type: "wishlist-toggle"; payload: { roomId: number } }
  | { type: "saved-search-check"; payload: { id: number } };

// ---------------------------------------------------------------------------
// Pure helpers (unit-tested — no IndexedDB needed)
// ---------------------------------------------------------------------------

/** Stable cache key from the exact query params used for the request. */
export function buildCacheKey(params: Record<string, string>): string {
  return Object.keys(params)
    .sort()
    .map((k) => `${k}=${params[k]}`)
    .join("&");
}

export function cacheFresh(ts: number, ttlMs: number, now: number = Date.now()): boolean {
  return now - ts < ttlMs;
}

function matchesQuery(room: Room, q: string): boolean {
  const needle = q.trim().toLowerCase();
  if (!needle) return true;
  const haystack = [room.name, room.description, room.area].join(" ").toLowerCase();
  return haystack.includes(needle);
}

/**
 * Re-apply the UI filters client-side over cached rooms (offline search).
 * Mirrors the server's filter semantics for the common filters.
 */
export function filterCachedRooms(rooms: Room[], filters: RoomFilters): Room[] {
  // Hoist to locals so the arrow closures see narrowed string values.
  const query = filters.query?.trim() ?? "";
  const area = filters.area && filters.area !== "All" ? filters.area : null;
  const type = filters.type && filters.type !== "All" ? filters.type.toLowerCase() : null;
  const gender = filters.gender && filters.gender !== "Any" ? filters.gender.toLowerCase() : null;
  const minPrice = filters.minPrice ? Number(filters.minPrice) : null;
  const maxPrice = filters.maxPrice ? Number(filters.maxPrice) : null;
  const wantAvailable = filters.available === "yes";
  const wantVerified = !!filters.verified;
  const amenities = filters.amenities ?? [];

  let out = rooms;
  if (query) out = out.filter((r) => matchesQuery(r, query));
  if (area) out = out.filter((r) => r.area === area);
  if (type) out = out.filter((r) => r.type.toLowerCase() === type);
  if (gender) out = out.filter((r) => r.gender.toLowerCase() === gender);
  if (minPrice !== null) out = out.filter((r) => r.price >= minPrice);
  if (maxPrice !== null) out = out.filter((r) => r.price <= maxPrice);
  if (wantAvailable) out = out.filter((r) => r.available);
  if (wantVerified) out = out.filter((r) => r.verified);
  if (amenities.length > 0)
    out = out.filter((r) => amenities.every((a) => r.amenities.includes(a)));

  if (filters.sort === "price-asc") out = [...out].sort((a, b) => a.price - b.price);
  else if (filters.sort === "price-desc") out = [...out].sort((a, b) => b.price - a.price);
  else if (filters.sort === "rating")
    out = [...out].sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0));

  return out;
}

// ---------------------------------------------------------------------------
// IndexedDB layer (thin, promise-based, graceful)
// ---------------------------------------------------------------------------

let dbPromise: Promise<IDBDatabase | null> | null = null;

function openDb(): Promise<IDBDatabase | null> {
  if (dbPromise) return dbPromise;
  dbPromise = new Promise((resolve) => {
    try {
      if (typeof indexedDB === "undefined") return resolve(null);
      const req = indexedDB.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains(STORE_ROOMS)) db.createObjectStore(STORE_ROOMS);
        if (!db.objectStoreNames.contains(STORE_ROOM)) db.createObjectStore(STORE_ROOM);
        if (!db.objectStoreNames.contains(STORE_QUEUE))
          db.createObjectStore(STORE_QUEUE, { keyPath: "id", autoIncrement: true });
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => resolve(null);
      req.onblocked = () => resolve(null);
    } catch {
      resolve(null);
    }
  });
  return dbPromise;
}

function tx<T>(
  store: string,
  mode: IDBTransactionMode,
  fn: (s: IDBObjectStore) => IDBRequest
): Promise<T | null> {
  return openDb().then(
    (db) =>
      new Promise<T | null>((resolve) => {
        if (!db) return resolve(null);
        try {
          const t = db.transaction(store, mode);
          const req = fn(t.objectStore(store));
          req.onsuccess = () => resolve(req.result as T);
          req.onerror = () => resolve(null);
        } catch {
          resolve(null);
        }
      })
  );
}

// ---- rooms (list results) ----
export async function setCachedRooms(key: string, list: CachedRoomList): Promise<void> {
  await tx(STORE_ROOMS, "readwrite", (s) => s.put(list, key));
}

export async function getCachedRooms(key: string): Promise<CachedRoomList | null> {
  return tx<CachedRoomList>(STORE_ROOMS, "readonly", (s) => s.get(key));
}

// ---- room (details) ----
export async function setCachedRoom(id: number, cached: CachedRoom): Promise<void> {
  await tx(STORE_ROOM, "readwrite", (s) => s.put(cached, String(id)));
}

export async function getCachedRoom(id: number): Promise<CachedRoom | null> {
  return tx<CachedRoom>(STORE_ROOM, "readonly", (s) => s.get(String(id)));
}

// ---- offline action queue ----
export async function enqueueAction(action: OfflineAction): Promise<void> {
  await tx(STORE_QUEUE, "readwrite", (s) => s.put({ ...action, ts: Date.now() }));
}

export async function listQueue(): Promise<OfflineAction[] | null> {
  return tx<OfflineAction[]>(STORE_QUEUE, "readonly", (s) => s.getAll());
}

export async function clearQueue(): Promise<void> {
  await tx(STORE_QUEUE, "readwrite", (s) => s.clear());
}
