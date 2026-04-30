"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import {
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
// Type → icon & color map — Venetian palette
// ---------------------------------------------------------------------------

type IconComponent = React.ComponentType<{ size?: number; color?: string; style?: React.CSSProperties }>;

const TYPE_CONFIG: Record<NotificationType, { Icon: IconComponent; color: string; glow: string }> = {
  info:    { Icon: Info,          color: "#9B4FD4", glow: "rgba(155,79,212,0.45)" },
  success: { Icon: CheckCircle2,  color: "#D4A000", glow: "rgba(212,160,0,0.45)"  },
  warning: { Icon: AlertTriangle, color: "#C07000", glow: "rgba(192,112,0,0.45)"  },
  error:   { Icon: XCircle,       color: "#FF1A1A", glow: "rgba(255,26,26,0.50)"  },
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
  const { Icon, color, glow } = TYPE_CONFIG[notification.type];

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
        margin: "0 6px 2px",
        borderRadius: 6,
        background: hovered
          ? "rgba(192,0,0,0.08)"
          : notification.read
          ? "transparent"
          : "rgba(192,0,0,0.04)",
        borderLeft: notification.read
          ? "2px solid rgba(138,0,0,0.20)"
          : `2px solid ${color}`,
        transition: "background 0.15s",
      }}
    >
      <Icon
        size={14}
        color={color}
        style={{ marginTop: 3, flexShrink: 0, filter: `drop-shadow(0 0 4px ${glow})` }}
      />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontSize: 12,
            fontWeight: notification.read ? 400 : 600,
            color: notification.read ? "var(--gray-silver, #b3b3b3)" : "var(--white-spectral, #f2f2f2)",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
            fontFamily: "var(--font-body)",
            letterSpacing: "0.02em",
          }}
        >
          {notification.title}
        </div>
        {notification.body && (
          <div
            style={{
              fontSize: 11,
              color: "#666",
              marginTop: 2,
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
              fontFamily: "var(--font-body)",
            }}
          >
            {notification.body}
          </div>
        )}
        <div
          style={{
            fontSize: 9,
            color: "#444",
            marginTop: 4,
            letterSpacing: "0.10em",
            fontFamily: "var(--font-mono)",
            textTransform: "uppercase",
          }}
        >
          {relativeTime(notification.timestamp)}
        </div>
      </div>
      {!notification.read && (
        <span
          style={{
            width: 5,
            height: 5,
            borderRadius: "50%",
            background: color,
            boxShadow: `0 0 6px ${glow}`,
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
          width: 44,
          height: 44,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          borderRadius: 8,
          background: "transparent",
          border: "1px solid transparent",
          cursor: "pointer",
          padding: 0,
          transition: "filter 0.2s",
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.filter = "drop-shadow(0 0 10px rgba(255,0,0,0.55))";
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.filter = unreadCount > 0
            ? "drop-shadow(0 0 6px rgba(255,0,0,0.35))"
            : "none";
        }}
      >
        <Image
          src="/icons/notification-bell.png"
          alt="Notifications"
          width={36}
          height={36}
          className="object-contain"
          style={{
            filter: unreadCount > 0
              ? "drop-shadow(0 0 6px rgba(255,0,0,0.60))"
              : "grayscale(0.3) opacity(0.7)",
            transition: "filter 0.2s",
            animation: unreadCount > 0 ? "bellRing 2.4s ease-in-out infinite" : "none",
          }}
        />
        {unreadCount > 0 && (
          <span
            style={{
              position: "absolute",
              top: 2,
              right: 2,
              minWidth: 17,
              height: 17,
              borderRadius: "50%",
              background: "radial-gradient(circle, #ff0000 0%, #8a0000 80%)",
              color: "#fff",
              fontSize: 9,
              fontWeight: 700,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              padding: "0 3px",
              lineHeight: 1,
              boxShadow: "0 0 8px rgba(255,0,0,0.7), 0 0 16px rgba(255,0,0,0.35)",
              animation: "badgePulse 1.8s ease-in-out infinite",
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
            top: "calc(100% + 10px)",
            right: 0,
            width: 340,
            maxHeight: 460,
            display: "flex",
            flexDirection: "column",
            background: "radial-gradient(circle at 30% 20%, #130000 0%, #080808 60%, #050505 100%)",
            border: "1px solid var(--red-dark)",
            borderRadius: 8,
            boxShadow: "inset 0 0 24px #220000, 0 0 20px rgba(192,0,0,0.30), 0 16px 48px rgba(0,0,0,0.90)",
            zIndex: 200,
            overflow: "hidden",
            animation: "pulseMarbre 2.4s ease-in-out infinite",
          }}
        >
          {/* Veinure décorative */}
          <div
            style={{
              position: "absolute",
              inset: 0,
              background: "linear-gradient(127deg, transparent 35%, rgba(138,0,0,0.04) 36%, rgba(138,0,0,0.04) 37%, transparent 38%), linear-gradient(220deg, transparent 42%, rgba(34,0,0,0.06) 43%, rgba(34,0,0,0.06) 44%, transparent 45%)",
              pointerEvents: "none",
              borderRadius: "inherit",
            }}
          />

          {/* ── Header ── */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "14px 16px 12px",
              borderBottom: "1px solid rgba(138,0,0,0.30)",
              background: "linear-gradient(90deg, transparent, rgba(138,0,0,0.06), transparent)",
              flexShrink: 0,
              position: "relative",
            }}
          >
            <span
              style={{
                fontSize: 10,
                fontWeight: 600,
                color: "var(--white-spectral, #f2f2f2)",
                display: "flex",
                alignItems: "center",
                gap: 8,
                fontFamily: "var(--font-title)",
                letterSpacing: "0.20em",
                textTransform: "uppercase",
                textShadow: "0 0 12px rgba(192,0,0,0.40)",
              }}
            >
              ✦ Alertes du Palais
              {unreadCount > 0 && (
                <span
                  style={{
                    padding: "1px 7px",
                    borderRadius: 10,
                    background: "rgba(192,0,0,0.15)",
                    border: "1px solid rgba(192,0,0,0.40)",
                    color: "#FF1A1A",
                    fontSize: 9,
                    fontWeight: 700,
                    fontFamily: "var(--font-mono)",
                    letterSpacing: "0.05em",
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
                  fontSize: 9,
                  color: "var(--gray-silver, #b3b3b3)",
                  background: "rgba(138,0,0,0.10)",
                  border: "1px solid rgba(138,0,0,0.25)",
                  borderRadius: 4,
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  gap: 4,
                  padding: "4px 8px",
                  fontFamily: "var(--font-mono)",
                  letterSpacing: "0.10em",
                  textTransform: "uppercase",
                  transition: "all 0.15s",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.color = "#FF1A1A";
                  e.currentTarget.style.borderColor = "rgba(192,0,0,0.50)";
                  e.currentTarget.style.background = "rgba(192,0,0,0.18)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.color = "var(--gray-silver, #b3b3b3)";
                  e.currentTarget.style.borderColor = "rgba(138,0,0,0.25)";
                  e.currentTarget.style.background = "rgba(138,0,0,0.10)";
                }}
              >
                <CheckCheck size={10} />
                Tout lire
              </button>
            )}
          </div>

          {/* ── List ── */}
          <div style={{ overflowY: "auto", flex: 1, padding: "8px 0 10px" }}>
            {notifications.length === 0 ? (
              <div
                style={{
                  padding: "32px 20px",
                  textAlign: "center",
                  color: "#444",
                  fontSize: 10,
                  fontFamily: "var(--font-title)",
                  letterSpacing: "0.18em",
                  textTransform: "uppercase",
                }}
              >
                — Silence du Palais —
              </div>
            ) : (
              notifications.map((n) => (
                <NotificationItem key={n.id} notification={n} onRead={markRead} />
              ))
            )}
          </div>

          {/* Ligne décorative bas */}
          <div
            style={{
              height: 1,
              background: "linear-gradient(90deg, transparent, var(--red-dark), var(--red-doge, #C00000), var(--red-dark), transparent)",
              opacity: 0.5,
              flexShrink: 0,
            }}
          />
        </div>
      )}
    </div>
  );
}



