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

export function useWsNotifications(): {
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

    const backendUrl =
      process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:18000";
    // Strip any trailing /api/v1 path before building the WebSocket URL
    // (NEXT_PUBLIC_BACKEND_URL already includes /api/v1 for HTTP calls)
    const wsBase = backendUrl.replace(/\/api\/v\d+\/?$/, "");
    // Replace http(s):// with ws(s):// for the WebSocket URL
    const wsUrl =
      wsBase.replace(/^http/, "ws") + "/api/v1/ws/notifications";

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
    };

    ws.onclose = () => {
      setIsConnected(false);
      wsRef.current = null;
      if (!unmountedRef.current) {
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
    connect();

    return () => {
      unmountedRef.current = true;
      if (reconnectTimer.current !== null) {
        clearTimeout(reconnectTimer.current);
      }
      wsRef.current?.close();
    };
  }, [connect]);

  const clearNotifications = useCallback(() => setNotifications([]), []);

  return { notifications, isConnected, clearNotifications };
}
