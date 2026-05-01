"use client";

/**
 * WsNotificationsBridge
 *
 * Mounts inside <NotificationProvider> and forwards real-time WebSocket
 * events to the existing app notification system via the custom DOM event
 * `app:notification` that NotificationProvider already listens to.
 *
 * Type mapping (backend `type` → AppNotificationType):
 *   crm:contact_created  → success
 *   crm:contact_updated  → info
 *   crm:contact_deleted  → warning
 *   crm:deal_*           → info / success / warning
 *   error / *            → error / info (fallback)
 */

import { useEffect } from "react";
import { useWsNotifications } from "@/hooks/useNotifications";
import type { NotificationType } from "./notification-provider";

/** Maps a backend event `type` to a UI notification type. */
function mapType(eventType: string): NotificationType {
  if (eventType.includes("delete") || eventType.includes("error")) return "warning";
  if (eventType.includes("create")) return "success";
  if (eventType.includes("update")) return "info";
  return "info";
}

/** Derives a human-readable title from the event type. */
function mapTitle(eventType: string): string {
  const map: Record<string, string> = {
    "crm:contact_created": "Contact créé",
    "crm:contact_updated": "Contact mis à jour",
    "crm:contact_deleted": "Contact supprimé",
    "crm:deal_created": "Deal créé",
    "crm:deal_updated": "Deal mis à jour",
    "crm:deal_deleted": "Deal supprimé",
  };
  return map[eventType] ?? eventType;
}

/** Derives an optional body string from the event payload. */
function mapBody(eventType: string, data: unknown): string | undefined {
  if (!data || typeof data !== "object") return undefined;
  const d = data as Record<string, unknown>;
  if (eventType.includes("contact")) {
    const name = [d.first_name, d.last_name].filter(Boolean).join(" ");
    return name || (d.email as string | undefined);
  }
  if (eventType.includes("deal")) {
    return (d.name ?? d.title ?? d.id) as string | undefined;
  }
  return undefined;
}

export function WsNotificationsBridge() {
  const { notifications } = useWsNotifications();

  // Each time a new WS notification arrives, forward it to the app event bus.
  // We track the last seen index so we only dispatch newly arrived items.
  useEffect(() => {
    if (notifications.length === 0) return;
    const latest = notifications[0]; // newest is prepended at index 0

    window.dispatchEvent(
      new CustomEvent("app:notification", {
        detail: {
          type: mapType(latest.type),
          title: mapTitle(latest.type),
          body: mapBody(latest.type, latest.data),
        },
      })
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [notifications.length]); // fire when a new item is prepended

  // This component renders nothing — it's a side-effect bridge only.
  return null;
}
