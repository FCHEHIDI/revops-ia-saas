"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type NotificationType = "info" | "success" | "warning" | "error";

export interface AppNotification {
  id: string;
  type: NotificationType;
  title: string;
  body?: string;
  timestamp: Date;
  read: boolean;
}

interface NotificationContextValue {
  notifications: AppNotification[];
  unreadCount: number;
  addNotification: (n: Omit<AppNotification, "id" | "timestamp" | "read">) => void;
  markRead: (id: string) => void;
  markAllRead: () => void;
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

const NotificationContext = createContext<NotificationContextValue | null>(null);

// ---------------------------------------------------------------------------
// localStorage helpers
// ---------------------------------------------------------------------------

const LS_KEY = "revops_notifications";

/** No seed data — notifications come from the backend WS or REST API only. */
const SEED: AppNotification[] = [];

interface SerializedNotification extends Omit<AppNotification, "timestamp"> {
  timestamp: string; // ISO string in storage
}

function loadFromStorage(): AppNotification[] | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return null;
    const parsed: SerializedNotification[] = JSON.parse(raw);
    if (!Array.isArray(parsed) || parsed.length === 0) return null;
    return parsed.map((n) => ({ ...n, timestamp: new Date(n.timestamp) }));
  } catch {
    return null;
  }
}

function saveToStorage(notifications: AppNotification[]): void {
  if (typeof window === "undefined") return;
  try {
    const serialized: SerializedNotification[] = notifications.map((n) => ({
      ...n,
      timestamp: n.timestamp.toISOString(),
    }));
    localStorage.setItem(LS_KEY, JSON.stringify(serialized));
  } catch {
    // Quota exceeded or private browsing — silently ignore
  }
}

function mergeWithSeed(stored: AppNotification[]): AppNotification[] {
  const storedIds = new Set(stored.map((n) => n.id));
  // Append seed items not already in storage (preserving their read state if present)
  const missingSeedItems = SEED.filter((s) => !storedIds.has(s.id));
  // Seed items at the end (oldest); stored (including WS notifications) at the front
  return [...stored, ...missingSeedItems];
}

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function NotificationProvider({ children }: { children: ReactNode }) {
  const [notifications, setNotifications] = useState<AppNotification[]>(() => {
    const stored = loadFromStorage();
    if (stored) return mergeWithSeed(stored);
    // First visit — initialize with seed and persist immediately
    saveToStorage(SEED);
    return SEED;
  });

  // Keep a ref so the persist effect only runs after the initial render,
  // not on hydration (avoids overwriting storage with stale closure state).
  const isFirstRender = useRef(true);

  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }
    saveToStorage(notifications);
  }, [notifications]);

  const addNotification = useCallback(
    (n: Omit<AppNotification, "id" | "timestamp" | "read">) => {
      setNotifications((prev) => [
        { ...n, id: crypto.randomUUID(), timestamp: new Date(), read: false },
        ...prev,
      ]);
    },
    []
  );

  const markRead = useCallback((id: string) => {
    setNotifications((prev) =>
      prev.map((n) => (n.id === id ? { ...n, read: true } : n))
    );
  }, []);

  const markAllRead = useCallback(() => {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
  }, []);

  // Listen for programmatic injection via custom DOM event:
  //   window.dispatchEvent(new CustomEvent("app:notification", { detail: { type, title, body } }))
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<Omit<AppNotification, "id" | "timestamp" | "read">>).detail;
      addNotification(detail);
    };
    window.addEventListener("app:notification", handler);
    return () => window.removeEventListener("app:notification", handler);
  }, [addNotification]);

  const unreadCount = notifications.filter((n) => !n.read).length;

  return (
    <NotificationContext.Provider
      value={{ notifications, unreadCount, addNotification, markRead, markAllRead }}
    >
      {children}
    </NotificationContext.Provider>
  );
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useNotifications(): NotificationContextValue {
  const ctx = useContext(NotificationContext);
  if (!ctx) {
    throw new Error("useNotifications must be used within <NotificationProvider>");
  }
  return ctx;
}
