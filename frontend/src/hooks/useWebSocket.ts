import { useCallback, useEffect, useRef, useState } from "react";
import { getAccessToken } from "../services/api";
import { env } from "../config/env";

// ============================================================
// useWebSocket — reusable, auto-reconnecting WebSocket hook.
//
// Connects to `${WS_BASE_URL}${path}?token=<jwt>`, re-reading the current
// access token from localStorage on every (re)connect attempt so a token
// refreshed in the meantime (by the axios interceptor) is picked up rather
// than retried forever with a stale one.
// ============================================================

const INITIAL_RECONNECT_DELAY_MS = 1000;
const MAX_RECONNECT_DELAY_MS = 30000;

export interface UseWebSocketOptions<T> {
  /** Skip connecting entirely (e.g. no active room selected, or logged out). */
  enabled?: boolean;
  /** Called for every parsed inbound message, in addition to `lastMessage`. */
  onMessage?: (data: T) => void;
}

export interface UseWebSocketReturn<T> {
  /** Serializes `data` as JSON and sends it. No-ops (with a console warning)
   * if the socket isn't currently open. */
  sendMessage: (data: unknown) => void;
  /** The most recently received message, parsed as JSON. */
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
  const reconnectAttemptRef = useRef(0);
  const shouldReconnectRef = useRef(false);

  // Keep the latest callback/path in refs so the connect() closure (created
  // once per effect run) never operates on stale values.
  const onMessageRef = useRef(options.onMessage);
  onMessageRef.current = options.onMessage;

  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimeoutRef.current != null) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (!enabled || !path) {
      return;
    }

    shouldReconnectRef.current = true;
    reconnectAttemptRef.current = 0;

    const connect = () => {
      const token = getAccessToken();
      if (!token) return; // Not signed in — nothing to connect with.

      const url = `${env.WS_BASE_URL}${path}?token=${encodeURIComponent(token)}`;
      const socket = new WebSocket(url);
      socketRef.current = socket;

      socket.onopen = () => {
        setIsConnected(true);
        reconnectAttemptRef.current = 0;
      };

      socket.onmessage = (event: MessageEvent<string>) => {
        try {
          const parsed = JSON.parse(event.data) as T;
          setLastMessage(parsed);
          onMessageRef.current?.(parsed);
        } catch {
          // Non-JSON frame — ignore rather than crash the socket handling.
        }
      };

      socket.onerror = () => {
        socket.close();
      };

      socket.onclose = () => {
        setIsConnected(false);
        socketRef.current = null;
        if (!shouldReconnectRef.current) return;

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
      socketRef.current?.close();
      socketRef.current = null;
      setIsConnected(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, enabled]);

  const sendMessage = useCallback((data: unknown) => {
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      console.warn("useWebSocket: tried to send while disconnected", data);
      return;
    }
    socket.send(JSON.stringify(data));
  }, []);

  return { sendMessage, lastMessage, isConnected };
}

export default useWebSocket;
