/**
 * useWebSocket reliability contract:
 *  - heartbeat pings are sent while open, pong frames are filtered from
 *    `lastMessage`, and a silent (half-open) connection is force-closed and
 *    reconnected with exponential backoff;
 *  - 4401 closes trigger a token refresh + immediate reconnect, bounded by
 *    AUTH_RETRY_LIMIT (a failed refresh or the limit gives up via onError);
 *  - 4403 closes stop reconnecting entirely;
 *  - `sendMessage` returns a boolean so callers never silently lose input.
 */
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../services/api";
import {
  AUTH_RETRY_LIMIT,
  HEARTBEAT_INTERVAL_MS,
  HEARTBEAT_TIMEOUT_MS,
  useWebSocket,
} from "./useWebSocket";

const ACCESS_TOKEN_KEY = "rentora_access";

vi.mock("../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../services/api")>();
  return {
    ...actual,
    refreshAccessToken: vi.fn(),
  };
});

const refreshMock = vi.mocked(api.refreshAccessToken);

// ---- Minimal controllable WebSocket double ----
class FakeWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;
  static readonly instances: FakeWebSocket[] = [];

  readonly url: string;
  readyState: number = FakeWebSocket.CONNECTING;
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: ((ev: { code: number }) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  send(data: string): void {
    this.sent.push(data);
  }

  close(code = 1000): void {
    if (this.readyState === FakeWebSocket.CLOSED) return;
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.({ code });
  }

  open(): void {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.();
  }

  receive(raw: string): void {
    this.onmessage?.({ data: raw });
  }
}

function render(overrides: { enabled?: boolean; onError?: () => void } = {}) {
  return renderHook(() =>
    useWebSocket("/ws/chat/1/", {
      ...overrides,
      WebSocketImpl: FakeWebSocket as unknown as typeof WebSocket,
    })
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  FakeWebSocket.instances.length = 0;
  localStorage.setItem(ACCESS_TOKEN_KEY, "test-access-token");
  refreshMock.mockResolvedValue("fresh-access-token");
});

afterEach(() => {
  localStorage.clear();
  vi.useRealTimers();
});

describe("useWebSocket heartbeat", () => {
  it("sends pings while open, filters pong frames, and force-closes half-open connections", () => {
    vi.useFakeTimers();
    const { result } = render();

    expect(FakeWebSocket.instances).toHaveLength(1);
    const socket = FakeWebSocket.instances[0];
    expect(socket.url).toContain("test-access-token");

    expect(result.current.isConnected).toBe(false);
    act(() => socket.open());
    expect(result.current.isConnected).toBe(true);

    // After one interval the client pings the server.
    act(() => vi.advanceTimersByTime(HEARTBEAT_INTERVAL_MS));
    expect(socket.sent).toContain(JSON.stringify({ type: "ping" }));

    // A pong answers the ping but must never surface as lastMessage.
    act(() => socket.receive(JSON.stringify({ type: "pong" })));
    expect(result.current.lastMessage).toBeNull();

    // Real inbound messages still surface.
    act(() => socket.receive(JSON.stringify({ type: "chat_message", id: 7 })));
    expect(result.current.lastMessage).toEqual({ type: "chat_message", id: 7 });

    // Now go quiet: no traffic for longer than the timeout means the socket
    // is half-open — the hook force-closes it and backoff-reconnects.
    act(() => vi.advanceTimersByTime(HEARTBEAT_TIMEOUT_MS + HEARTBEAT_INTERVAL_MS));
    expect(FakeWebSocket.instances[0].readyState).toBe(FakeWebSocket.CLOSED);
    expect(result.current.isConnected).toBe(false);

    // First reconnect lands after the initial backoff delay (1s).
    act(() => vi.runOnlyPendingTimers());
    expect(FakeWebSocket.instances).toHaveLength(2);
  });

  it("does not ping before the socket is open, and stops pinging after close", () => {
    vi.useFakeTimers();
    const { unmount } = render();
    const socket = FakeWebSocket.instances[0];

    act(() => vi.advanceTimersByTime(HEARTBEAT_INTERVAL_MS * 2));
    expect(socket.sent).toHaveLength(0);

    act(() => socket.open());
    act(() => vi.advanceTimersByTime(HEARTBEAT_INTERVAL_MS));
    expect(socket.sent).toContain(JSON.stringify({ type: "ping" }));
    expect(socket.sent).toHaveLength(1);

    unmount();
    act(() => vi.advanceTimersByTime(HEARTBEAT_INTERVAL_MS * 2));
    expect(socket.sent).toHaveLength(1);
  });
});

describe("useWebSocket sendMessage", () => {
  it("returns false (and sends nothing) while disconnected", () => {
    const { result } = render();

    const sent = result.current.sendMessage({ type: "message", content: "hi" });
    expect(sent).toBe(false);
    expect(FakeWebSocket.instances[0].sent).toHaveLength(0);
  });

  it("returns true and serializes JSON when open", () => {
    const { result } = render();
    const socket = FakeWebSocket.instances[0];
    act(() => socket.open());

    const sent = result.current.sendMessage({ type: "message", content: "hi" });
    expect(sent).toBe(true);
    expect(socket.sent).toEqual([JSON.stringify({ type: "message", content: "hi" })]);
  });

  it("ignores non-JSON inbound frames without crashing", () => {
    const { result } = render();
    const socket = FakeWebSocket.instances[0];

    act(() => socket.receive("not-json"));
    expect(result.current.lastMessage).toBeNull();
  });
});

describe("useWebSocket close-code handling", () => {
  it("4401 refreshes the token and reconnects, then gives up after the retry limit", async () => {
    const onError = vi.fn();
    const { result } = render({ onError });

    expect(FakeWebSocket.instances).toHaveLength(1);
    act(() => FakeWebSocket.instances[0].open());

    // Each 4401 (with no healthy traffic in between) eats one retry budget.
    for (let closeCount = 1; closeCount <= AUTH_RETRY_LIMIT + 1; closeCount++) {
      act(() => FakeWebSocket.instances[closeCount - 1].close(4401));

      if (closeCount <= AUTH_RETRY_LIMIT) {
        await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(closeCount + 1));
        act(() => FakeWebSocket.instances[closeCount].open());
      }
    }

    expect(refreshMock).toHaveBeenCalledTimes(AUTH_RETRY_LIMIT);
    // The final 4401 exceeded the budget: no further socket, session give-up.
    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(AUTH_RETRY_LIMIT + 1));
    expect(onError).toHaveBeenCalledTimes(1);
    expect(onError).toHaveBeenCalledWith({ type: "auth_expired" });
    expect(result.current.isConnected).toBe(false);
  });

  it("a failed refresh stops reconnecting with auth_expired", async () => {
    refreshMock.mockRejectedValue(new Error("refresh token invalid"));
    const onError = vi.fn();
    render({ onError });

    act(() => FakeWebSocket.instances[0].open());
    act(() => FakeWebSocket.instances[0].close(4401));

    await waitFor(() => expect(onError).toHaveBeenCalledWith({ type: "auth_expired" }));
    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it("healthy inbound traffic resets the 4401 budget", async () => {
    const onError = vi.fn();
    render({ onError });

    act(() => FakeWebSocket.instances[0].open());
    act(() => FakeWebSocket.instances[0].close(4401));
    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(2));

    // Second socket proves itself healthy with a frame, then gets closed 4401.
    act(() => FakeWebSocket.instances[1].open());
    act(() => FakeWebSocket.instances[1].receive(JSON.stringify({ type: "chat_message" })));
    act(() => FakeWebSocket.instances[1].close(4401));

    // The reset budget means this reconnect still happens (no auth_expired).
    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(3));
    expect(onError).not.toHaveBeenCalled();
  });

  it("4403 stops reconnecting and reports forbidden", async () => {
    const onError = vi.fn();
    render({ onError });

    act(() => FakeWebSocket.instances[0].open());
    act(() => FakeWebSocket.instances[0].close(4403));

    await waitFor(() => expect(onError).toHaveBeenCalledWith({ type: "forbidden" }));
    expect(FakeWebSocket.instances).toHaveLength(1);
  });
});
