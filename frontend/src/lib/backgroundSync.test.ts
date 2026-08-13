import { describe, it, expect, vi, beforeEach } from "vitest";
import { replayQueue } from "./backgroundSync";
import { requestPeriodicRefresh } from "./periodicSync";
import * as offlineDb from "./offlineDb";

const mocks = vi.hoisted(() => ({
  apiPost: vi.fn(),
}));

vi.mock("../services/api", () => ({
  api: { post: (...args: unknown[]) => mocks.apiPost(...args) },
}));

const actions = (): offlineDb.OfflineAction[] => [
  { type: "wishlist-toggle", payload: { roomId: 7 } },
  { type: "saved-search-check", payload: { id: 3 } },
];

describe("replayQueue", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    mocks.apiPost.mockReset().mockResolvedValue({ data: {} });
    vi.spyOn(offlineDb, "listQueue").mockResolvedValue(actions());
  });

  it("replays each queued action once and clears the queue", async () => {
    const clear = vi.spyOn(offlineDb, "clearQueue").mockResolvedValue(undefined);

    const count = await replayQueue();
    expect(count).toBe(2);
    expect(mocks.apiPost).toHaveBeenCalledTimes(2);
    expect(mocks.apiPost).toHaveBeenNthCalledWith(1, "/wishlist/toggle/", { room_id: 7 });
    expect(mocks.apiPost).toHaveBeenNthCalledWith(2, "/saved-searches/3/check/");
    expect(clear).toHaveBeenCalled();
  });

  it("keeps failed actions queued for retry (never drops silently)", async () => {
    let calls = 0;
    mocks.apiPost.mockImplementation(async () => {
      calls += 1;
      if (calls === 1) throw new Error("still offline");
      return { data: {} };
    });
    const enqueue = vi.spyOn(offlineDb, "enqueueAction").mockResolvedValue(undefined);
    vi.spyOn(offlineDb, "clearQueue").mockResolvedValue(undefined);

    const count = await replayQueue();
    expect(count).toBe(1);
    // The failed wishlist toggle was re-queued for the next attempt.
    expect(enqueue).toHaveBeenCalledWith({ type: "wishlist-toggle", payload: { roomId: 7 } });
  });

  it("returns 0 when the queue is empty", async () => {
    vi.spyOn(offlineDb, "listQueue").mockResolvedValue([]);
    expect(await replayQueue()).toBe(0);
  });
});

describe("requestPeriodicRefresh", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("reports unsupported when periodicSync is missing", async () => {
    const reg = {} as ServiceWorkerRegistration;
    expect(await requestPeriodicRefresh(reg)).toBe("unsupported");
  });

  function mockPermissions(queryImpl: () => Promise<PermissionStatus>) {
    Object.defineProperty(navigator, "permissions", {
      value: { query: queryImpl },
      configurable: true,
    });
  }

  it("registers when permission granted", async () => {
    const register = vi.fn().mockResolvedValue(undefined);
    const getTags = vi.fn().mockResolvedValue([]);
    const reg = {
      periodicSync: { register, getTags },
    } as unknown as ServiceWorkerRegistration;
    mockPermissions(async () => ({ state: "granted" }) as PermissionStatus);

    expect(await requestPeriodicRefresh(reg)).toBe("registered");
    expect(register).toHaveBeenCalledWith("rentora-refresh", { minInterval: 86400000 });
  });

  it("does not double-register an existing tag", async () => {
    const register = vi.fn();
    const getTags = vi.fn().mockResolvedValue(["rentora-refresh"]);
    const reg = { periodicSync: { register, getTags } } as unknown as ServiceWorkerRegistration;
    mockPermissions(async () => ({ state: "granted" }) as PermissionStatus);

    expect(await requestPeriodicRefresh(reg)).toBe("already");
    expect(register).not.toHaveBeenCalled();
  });

  it("degrades when the permission query throws (non-Chromium)", async () => {
    const reg = {
      periodicSync: { register: vi.fn(), getTags: vi.fn() },
    } as unknown as ServiceWorkerRegistration;
    mockPermissions(async () => {
      throw new Error("not supported");
    });

    expect(await requestPeriodicRefresh(reg)).toBe("unsupported");
  });
});
