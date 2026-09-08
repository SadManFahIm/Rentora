import { useCallback, useEffect, useRef, useState } from "react";
import { getAccessToken, refreshAccessToken } from "../services/api";
import { env } from "../config/env";

// ============================================================
// useWebSocket — reusable, auto-reconnecting WebSocket hook.
//
// Connects to `${WS_BASE_URL}${path}?token=<jwt>`, re-reading the current
// access token from localStorage on every (re)connect attempt so a token
// refreshed in the meantime (by the axios interceptor) is picked up rather
// than retried forever with a stale one.
//
// Reliability (browser WS can't see protocol pings, so this is app-level):
//  - Heartbeat: while connected, sends `{"type":"ping"}` every
//    HEARTBEAT_INTERVAL_MS and expects *any* inbound frame as liveness. If no
//    server traffic arrives for HEARTBEAT_TIMEOUT_MS the socket is force-
//    closed so a half-open connection is detected and reconnected instead of
//    silently sitting dead. The server answers ping frames with
//    `{"type":"pong"}`, which is consumed here and never surfaced to callers.
//  - Close codes: 4401 (expired JWT) refreshes the access token once per
//    close and reconnects immediately, bounded by AUTH_RETRY_LIMIT on *4403*
//    or a failed refresh it gives up (onError("auth_expired")) instead of
//    looping forever.
//  - `sendMessage` returns a boolean so callers can stop clearing input /
//    surface an error instead of silently dropping the message.
// ============================================================

export const HEARTBEAT_INTERVAL_MS = 25000;
export const HEARTBEAT_TIMEOUT_MS = 60000;
const INITIAL_RECONNECT_DELAY_MS = 1000;
const MAX_RECONNECT_DELAY_MS = 30000;
export const AUTH_RETRY_LIMIT = 3;

/** Server close codes we act on (mirrors backend chat/consumers.py). */
const WS_CLOSE_UNAUTHENTICATED = 4401;
const WS_CLOSE_FORBIDDEN = 4403;

export type WebSocketErrorInfo = { type: "auth_expired" } | { type: "forbidden" };

export interface UseWebSocketOptions<T> {
  /** Skip connecting entirely (e.g. no active room selected, or logged out). */
  enabled?: boolean;
  /** Called for every parsed inbound message, in addition to `lastMessage`. */
  onMessage?: (data: T) => void;
  /** Called when the connection gives up on a recoverable failure: the auth
   * token can't be refreshed (or the retry limit is hit) or the server
   * rejected the session (4403). */
  onError?: (info: WebSocketErrorInfo) => void;
  /** Test seam: the WebSocket constructor to use (defaults to the browser's). */
  WebSocketImpl?: typeof WebSocket;
}

export interface UseWebSocketReturn<T> {
  /** Serializes `data` as JSON and sends it. Returns `true` on success;
   * returns `false` (sending nothing) if the socket isn't open so callers can
   * keep their input and tell the user about the failure. */
  sendMessage: (data: unknown) => boolean;
  /** The most recently received message, parsed as JSON (heartbeat `pong`
   * frames are filtered out). */
  lastMessage: T | null;
  isConnected: boolean;
}

/**
 * @param path e.g. "/ws/chat/12/" or "/ws/notifications/" — or `null`/`""` to
 * stay disconnected (the hook cleans up any existing connection when the
 * path changes to a falsy value, e.g. no room selected).
 */
export function useWebSocket<T = unknown>(
  path: string | null,
  options: UseWebSocketOptions<T> = {}
): UseWebSocketReturn<T> {
  const { enabled = true } = options;

  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<T | null>(null);

  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const heartbeatIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const reconnectAttemptRef = useRef(0);
  const authClosedRef = useRef(0);
  const shouldReconnectRef = useRef(false);
  const lastActivityAtRef = useRef(0);

  // Keep the latest callbacks/constructor in refs so the connect() closure
  // (created once per effect run) never operates on stale values.
  const onMessageRef = useRef(options.onMessage);
  onMessageRef.current = options.onMessage;
  const onErrorRef = useRef(options.onError);
  onErrorRef.current = options.onError;
  const WebSocketImplRef = useRef(options.WebSocketImpl ?? WebSocket);
  WebSocketImplRef.current = options.WebSocketImpl ?? WebSocket;

  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimeoutRef.current != null) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
  }, []);

  const clearHeartbeat = useCallback(() => {
    if (heartbeatIntervalRef.current != null) {
      clearInterval(heartbeatIntervalRef.current);
      heartbeatIntervalRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (!enabled || !path) {
      return;
    }

    shouldReconnectRef.current = true;
    reconnectAttemptRef.current = 0;
    authClosedRef.current = 0;

    const WSImpl = WebSocketImplRef.current;

    const startHeartbeat = (socket: WebSocket) => {
      lastActivityAtRef.current = Date.now();
      heartbeatIntervalRef.current = setInterval(() => {
        if (Date.now() - lastActivityAtRef.current > HEARTBEAT_TIMEOUT_MS) {
          // No server traffic for too long — the connection is likely
          // half-open. Close it so onclose fires and we reconnect.
          socket.close();
          return;
        }
        if (socket.readyState === WSImpl.OPEN) {
          socket.send(JSON.stringify({ type: "ping" }));
        }
      }, HEARTBEAT_INTERVAL_MS);
    };

    const connect = () => {
      const token = getAccessToken();
      if (!token) return; // Not signed in — nothing to connect with.

      const url = `${env.WS_BASE_URL}${path}?token=${encodeURIComponent(token)}`;
      const socket = new WSImpl(url);
      socketRef.current = socket;

      socket.onopen = () => {
        setIsConnected(true);
        reconnectAttemptRef.current = 0;
        startHeartbeat(socket);
      };

      socket.onmessage = (event: MessageEvent<string>) => {
        lastActivityAtRef.current = Date.now();
        // Any inbound frame means the server accepted the session, so a
        // healthy socket resets the consecutive-4401 budget.
        authClosedRef.current = 0;
        if (typeof event.data !== "string") return; // Binary/Blob frames unsupported.
        let parsed: { type?: string } | null;
        try {
          parsed = JSON.parse(event.data) as { type?: string } | null;
        } catch {
          return; // Non-JSON frame — ignore rather than crash the socket handling.
        }
        if (!parsed || parsed.type === "pong") return; // Heartbeat answer — not for callers.
        const data = parsed as T;
        setLastMessage(data);
        onMessageRef.current?.(data);
      };

      socket.onerror = () => {
        socket.close();
      };

      socket.onclose = (event: { code: number }) => {
        setIsConnected(false);
        socketRef.current = null;
        clearHeartbeat();
        if (!shouldReconnectRef.current) return;

        if (event.code === WS_CLOSE_UNAUTHENTICATED) {
          // Access token expired server-side: refresh it (single-flight is
          // handled inside api.ts) and reconnect immediately, bounded.
          if (authClosedRef.current >= AUTH_RETRY_LIMIT) {
            shouldReconnectRef.current = false;
            onErrorRef.current?.({ type: "auth_expired" });
            return;
          }
          authClosedRef.current += 1;
          refreshAccessToken()
            .then(() => {
              if (!shouldReconnectRef.current) return;
              reconnectAttemptRef.current = 0;
              connect();
            })
            .catch(() => {
              shouldReconnectRef.current = false;
              onErrorRef.current?.({ type: "auth_expired" });
            });
          return;
        }

        if (event.code === WS_CLOSE_FORBIDDEN) {
          // Session rejected outright (e.g. not a room member) — no point
          // reconnecting.
          shouldReconnectRef.current = false;
          onErrorRef.current?.({ type: "forbidden" });
          return;
        }

        const attempt = reconnectAttemptRef.current;
        const delay = Math.min(INITIAL_RECONNECT_DELAY_MS * 2 ** attempt, MAX_RECONNECT_DELAY_MS);
        reconnectAttemptRef.current = attempt + 1;
        clearReconnectTimer();
        reconnectTimeoutRef.current = setTimeout(() => {
          if (shouldReconnectRef.current) connect();
        }, delay);
      };
    };

    connect();

    return () => {
      shouldReconnectRef.current = false;
      clearReconnectTimer();
      clearHeartbeat();
      socketRef.current?.close();
      socketRef.current = null;
      setIsConnected(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, enabled]);

  const sendMessage = useCallback((data: unknown): boolean => {
    const socket = socketRef.current;
    const WSImpl = WebSocketImplRef.current;
    if (!socket || socket.readyState !== WSImpl.OPEN) {
      return false;
    }
    socket.send(JSON.stringify(data));
    return true;
  }, []);

  return { sendMessage, lastMessage, isConnected };
}

export default useWebSocket;
