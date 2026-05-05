/**
 * useNotifications — WebSocket hook for real-time tenant notifications.
 *
 * Connects to /api/v1/ws/notifications on the backend, handles reconnection,
 * heartbeat pong replies, and accumulates incoming events in state.
 *
 * Usage:
 *   const { notifications, isConnected } = useNotifications();
 *
 * The backend sends frames of the shape:
 *   { type: "connected",             tenant_id: string }
 *   { type: "ping",                  ts: number }
 *   { type: "crm:contact_created",   data: unknown }
 *   { type: "crm:contact_updated",   data: unknown }
 *   { type: "crm:contact_deleted",   data: { id: string } }
 *
 * The hook replies to "ping" with the text "ping" and ignores "connected" frames
 * (they are not stored in `notifications`).
 */

import { useCallback, useEffect, useRef, useState } from "react";

export interface Notification {
  type: string;
  data?: unknown;
  tenant_id?: string;
  timestamp: number;
}

/** Maximum number of notifications kept in memory. */
const MAX_NOTIFICATIONS = 50;

/** Reconnect delay in ms after an unexpected close. */
const RECONNECT_DELAY_MS = 3_000;

/** Internal frame types that are not surfaced as user notifications. */
const SILENT_TYPES = new Set(["connected", "ping", "pong"]);

/**
 * WebSocket close codes that must NOT trigger a reconnection attempt:
 *  4001 — backend rejected the connection (not authenticated / invalid token)
 *  1000 — normal closure (intentional disconnect, e.g. logout)
 *  1001 — endpoint going away (server shutdown)
 */
const NO_RECONNECT_CODES = new Set([4001, 1000, 1001]);

export function useWsNotifications(enabled: boolean = true): {
  notifications: Notification[];
  isConnected: boolean;
  clearNotifications: () => void;
} {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [isConnected, setIsConnected] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  /** Set to true when the hook unmounts so we stop reconnecting. */
  const unmountedRef = useRef(false);

  const connect = useCallback(() => {
    if (unmountedRef.current) return;

    // Connect directly to the backend (Next.js rewrites do not proxy WebSocket
    // upgrades).  Cookies are domain-scoped (port-independent) so the
    // access_token cookie set at :3000 is sent to the backend at :18000.
    const backendUrl =
      process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://127.0.0.1:18000/api/v1";
    const wsBase = backendUrl
      .replace(/\/api\/v\d+\/?$/, "")
      .replace("localhost", "127.0.0.1");
    const wsUrl = wsBase.replace(/^http/, "ws") + "/api/v1/ws/notifications";

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      // React Strict Mode cleanup may have fired while we were still CONNECTING.
      // Now that the socket is OPEN we can close it cleanly (no browser warning).
      if (unmountedRef.current) {
        ws.close(1000);
        return;
      }
      setIsConnected(true);
    };

    ws.onclose = (event: CloseEvent) => {
      setIsConnected(false);
      wsRef.current = null;
      // Only reconnect for unexpected network drops — never for auth rejection
      // (4001), normal closure (1000), or endpoint going away (1001).
      const shouldReconnect =
        !unmountedRef.current && !NO_RECONNECT_CODES.has(event.code);
      if (shouldReconnect) {
        reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY_MS);
      }
    };

    ws.onerror = () => {
      // onclose fires right after onerror; reconnect is handled there.
      ws.close();
    };

    ws.onmessage = (evt: MessageEvent<string>) => {
      let payload: Record<string, unknown>;
      try {
        payload = JSON.parse(evt.data) as Record<string, unknown>;
      } catch {
        // Ignore malformed frames
        return;
      }

      const type = payload.type as string | undefined;

      // Reply to server pings so the backend knows the client is alive.
      if (type === "ping") {
        ws.send(JSON.stringify({ type: "pong" }));
        return;
      }

      // Don't store internal protocol frames.
      if (!type || SILENT_TYPES.has(type)) return;

      const notification: Notification = {
        type,
        data: payload.data,
        tenant_id: payload.tenant_id as string | undefined,
        timestamp: Date.now(),
      };

      setNotifications((prev) =>
        [notification, ...prev].slice(0, MAX_NOTIFICATIONS),
      );
    };
  }, []);

  useEffect(() => {
    unmountedRef.current = false;

    if (enabled) {
      connect();
    }

    return () => {
      unmountedRef.current = true;
      if (reconnectTimer.current !== null) {
        clearTimeout(reconnectTimer.current);
      }
      // Only close if the socket is already OPEN or CLOSING.
      // If it's still CONNECTING, calling close() with a code throws
      // "WebSocket is closed before the connection is established" in the browser.
      // onopen will detect unmountedRef.current === true and close cleanly then.
      if (
        wsRef.current &&
        wsRef.current.readyState !== WebSocket.CONNECTING
      ) {
        wsRef.current.close(1000);
      }
    };
  }, [connect, enabled]);

  const clearNotifications = useCallback(() => setNotifications([]), []);

  return { notifications, isConnected, clearNotifications };
}
