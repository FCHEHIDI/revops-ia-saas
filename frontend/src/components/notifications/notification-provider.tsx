"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
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
// Seed data (simulates recent activity)
// ---------------------------------------------------------------------------

const SEED: Omit<AppNotification, "id" | "timestamp" | "read">[] = [
  {
    type: "warning",
    title: "Paiement en retard",
    body: "Acme Corp — facture #INV-2087 échue depuis 7 jours",
  },
  {
    type: "success",
    title: "Séquence terminée",
    body: "«Onboarding Q2» — 12 contacts ont complété tous les steps",
  },
  {
    type: "info",
    title: "Nouveau deal créé",
    body: "Pipeline Expansion — FinTech Solutions (85 000 €)",
  },
];

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function NotificationProvider({ children }: { children: ReactNode }) {
  const [notifications, setNotifications] = useState<AppNotification[]>(() =>
    SEED.map((n, i) => ({
      ...n,
      id: crypto.randomUUID(),
      timestamp: new Date(Date.now() - (SEED.length - i) * 5 * 60_000),
      read: false,
    }))
  );

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
