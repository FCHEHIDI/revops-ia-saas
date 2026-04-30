"use client";

import { useEffect, useRef, useState } from "react";
import {
  Bell,
  BellRing,
  CheckCheck,
  AlertTriangle,
  CheckCircle2,
  Info,
  XCircle,
} from "lucide-react";
import {
  useNotifications,
  type AppNotification,
  type NotificationType,
} from "./notification-provider";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function relativeTime(date: Date): string {
  const diff = Date.now() - date.getTime();
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) return "à l'instant";
  if (minutes < 60) return `il y a ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `il y a ${hours}h`;
  return `il y a ${Math.floor(hours / 24)}j`;
}

// ---------------------------------------------------------------------------
// Type → icon & color map
// ---------------------------------------------------------------------------

type IconComponent = React.ComponentType<{ size?: number; color?: string; style?: React.CSSProperties }>;

const TYPE_CONFIG: Record<NotificationType, { Icon: IconComponent; color: string }> = {
  info:    { Icon: Info,          color: "#50b4ff" },
  success: { Icon: CheckCircle2,  color: "#78ffa0" },
  warning: { Icon: AlertTriangle, color: "#ffb850" },
  error:   { Icon: XCircle,       color: "#ff5050" },
};

// ---------------------------------------------------------------------------
// NotificationItem
// ---------------------------------------------------------------------------

function NotificationItem({
  notification,
  onRead,
}: {
  notification: AppNotification;
  onRead: (id: string) => void;
}) {
  const [hovered, setHovered] = useState(false);
  const { Icon, color } = TYPE_CONFIG[notification.type];

  return (
    <div
      onClick={() => onRead(notification.id)}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: "flex",
        gap: 10,
        padding: "10px 14px",
        cursor: "pointer",
        borderRadius: 8,
        margin: "0 4px",
        background: hovered
          ? "rgba(255,255,255,0.03)"
          : notification.read
          ? "transparent"
          : "rgba(80,180,255,0.03)",
        borderLeft: notification.read
          ? "2px solid transparent"
          : `2px solid ${color}`,
        transition: "background 0.15s",
      }}
    >
      <Icon
        size={15}
        color={color}
        style={{ marginTop: 2, flexShrink: 0 }}
      />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontSize: 13,
            fontWeight: notification.read ? 400 : 600,
            color: "var(--text-primary, #f5f5f5)",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {notification.title}
        </div>
        {notification.body && (
          <div
            style={{
              fontSize: 11,
              color: "var(--text-secondary, #999)",
              marginTop: 2,
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
          >
            {notification.body}
          </div>
        )}
        <div style={{ fontSize: 10, color: "#555", marginTop: 4 }}>
          {relativeTime(notification.timestamp)}
        </div>
      </div>
      {!notification.read && (
        <span
          style={{
            width: 6,
            height: 6,
            borderRadius: "50%",
            background: color,
            flexShrink: 0,
            alignSelf: "center",
          }}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// NotificationPanel — bell button + dropdown
// ---------------------------------------------------------------------------

export function NotificationPanel() {
  const { notifications, unreadCount, markRead, markAllRead } = useNotifications();
  const [open, setOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);

  // Close when clicking outside
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  return (
    <div ref={panelRef} style={{ position: "relative" }}>
      {/* ── Bell button ── */}
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label={`Notifications${unreadCount > 0 ? ` (${unreadCount} non lues)` : ""}`}
        style={{
          position: "relative",
          width: 36,
          height: 36,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          borderRadius: 8,
          background: open ? "rgba(255,255,255,0.06)" : "transparent",
          border: `1px solid ${open ? "rgba(255,255,255,0.08)" : "transparent"}`,
          cursor: "pointer",
          transition: "background 0.15s, border-color 0.15s",
        }}
        onMouseEnter={(e) => {
          if (!open) {
            e.currentTarget.style.background = "rgba(255,255,255,0.04)";
            e.currentTarget.style.borderColor = "rgba(255,255,255,0.07)";
          }
        }}
        onMouseLeave={(e) => {
          if (!open) {
            e.currentTarget.style.background = "transparent";
            e.currentTarget.style.borderColor = "transparent";
          }
        }}
      >
        {unreadCount > 0 ? (
          <BellRing size={18} color="#f5f5f5" />
        ) : (
          <Bell size={18} color="#666" />
        )}

        {/* Unread badge */}
        {unreadCount > 0 && (
          <span
            style={{
              position: "absolute",
              top: 4,
              right: 4,
              minWidth: 16,
              height: 16,
              borderRadius: 8,
              background: "#ff5050",
              color: "#fff",
              fontSize: 9,
              fontWeight: 700,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              padding: "0 3px",
              lineHeight: 1,
              pointerEvents: "none",
            }}
          >
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>

      {/* ── Dropdown panel ── */}
      {open && (
        <div
          style={{
            position: "absolute",
            top: "calc(100% + 8px)",
            right: 0,
            width: 320,
            maxHeight: 440,
            display: "flex",
            flexDirection: "column",
            background: "#111",
            border: "1px solid rgba(255,255,255,0.09)",
            borderRadius: 12,
            boxShadow: "0 12px 40px rgba(0,0,0,0.7)",
            zIndex: 200,
            overflow: "hidden",
          }}
        >
          {/* Header */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "12px 14px 10px",
              borderBottom: "1px solid rgba(255,255,255,0.06)",
              flexShrink: 0,
            }}
          >
            <span
              style={{
                fontSize: 13,
                fontWeight: 600,
                color: "#f5f5f5",
                display: "flex",
                alignItems: "center",
                gap: 8,
              }}
            >
              Notifications
              {unreadCount > 0 && (
                <span
                  style={{
                    padding: "1px 7px",
                    borderRadius: 10,
                    background: "rgba(255,80,80,0.12)",
                    color: "#ff5050",
                    fontSize: 11,
                    fontWeight: 700,
                  }}
                >
                  {unreadCount}
                </span>
              )}
            </span>

            {unreadCount > 0 && (
              <button
                onClick={markAllRead}
                style={{
                  fontSize: 11,
                  color: "#50b4ff",
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  gap: 4,
                  padding: 0,
                }}
              >
                <CheckCheck size={12} />
                Tout lire
              </button>
            )}
          </div>

          {/* List */}
          <div style={{ overflowY: "auto", flex: 1, padding: "6px 0 8px" }}>
            {notifications.length === 0 ? (
              <div
                style={{
                  padding: 28,
                  textAlign: "center",
                  color: "#444",
                  fontSize: 13,
                }}
              >
                Aucune notification
              </div>
            ) : (
              notifications.map((n) => (
                <NotificationItem key={n.id} notification={n} onRead={markRead} />
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
