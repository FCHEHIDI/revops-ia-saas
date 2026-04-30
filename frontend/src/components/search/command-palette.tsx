"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useRouter } from "next/navigation";
import {
  Search,
  Users,
  Workflow,
  LayoutDashboard,
  BarChart2,
  FileText,
  CreditCard,
} from "lucide-react";
import { crmApi, sequencesApi } from "@/lib/api";
import type { Contact, Sequence } from "@/types";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const KBD: React.CSSProperties = {
  fontSize: 9,
  color: "#555",
  background: "rgba(255,255,255,0.05)",
  border: "1px solid rgba(255,255,255,0.08)",
  borderRadius: 3,
  padding: "2px 5px",
  marginRight: 2,
};

interface PageShortcut {
  label: string;
  href: string;
  Icon: React.ComponentType<{ size?: number; color?: string }>;
}

const PAGE_SHORTCUTS: PageShortcut[] = [
  { label: "Dashboard",   href: "/dashboard",  Icon: LayoutDashboard },
  { label: "CRM",         href: "/crm",        Icon: Users           },
  { label: "Analytics",   href: "/analytics",  Icon: BarChart2       },
  { label: "Séquences",   href: "/sequences",  Icon: Workflow        },
  { label: "Documents",   href: "/documents",  Icon: FileText        },
  { label: "Facturation", href: "/billing",    Icon: CreditCard      },
];

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ResultSection({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div style={{ padding: "8px 0 2px" }}>
      <div
        style={{
          fontSize: 10,
          fontWeight: 600,
          color: "#444",
          textTransform: "uppercase",
          letterSpacing: "0.08em",
          padding: "0 16px 6px",
        }}
      >
        {label}
      </div>
      {children}
    </div>
  );
}

function ResultRow({
  icon,
  label,
  subtitle,
  selected,
  onClick,
}: {
  icon: ReactNode;
  label: string;
  subtitle?: string;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <div
      onClick={onClick}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        padding: "8px 16px",
        cursor: "pointer",
        background: selected ? "rgba(80,180,255,0.08)" : "transparent",
        borderLeft: selected ? "2px solid #50b4ff" : "2px solid transparent",
        transition: "background 0.1s",
      }}
    >
      <span style={{ flexShrink: 0, display: "flex", alignItems: "center" }}>
        {icon}
      </span>
      <span style={{ flex: 1, minWidth: 0 }}>
        <span
          style={{
            display: "block",
            fontSize: 13,
            color: "#f5f5f5",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {label}
        </span>
        {subtitle && (
          <span
            style={{
              display: "block",
              fontSize: 11,
              color: "#555",
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
          >
            {subtitle}
          </span>
        )}
      </span>
    </div>
  );
}

function ContactAvatar({ contact }: { contact: Contact }) {
  return (
    <span
      style={{
        width: 22,
        height: 22,
        borderRadius: "50%",
        background: "#1e3a5f",
        color: "#50b4ff",
        fontSize: 9,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontWeight: 700,
        flexShrink: 0,
      }}
    >
      {contact.first_name[0]}
      {contact.last_name[0]}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Navigable item type (flat list for keyboard nav)
// ---------------------------------------------------------------------------

interface NavItem {
  key: string;
  label: string;
  subtitle?: string;
  icon: ReactNode;
  action: () => void;
  section: string;
}

// ---------------------------------------------------------------------------
// CommandPalette — mount at layout level, keyboard shortcut Ctrl+K / Cmd+K
// ---------------------------------------------------------------------------

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [sequences, setSequences] = useState<Sequence[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const router = useRouter();

  const navigate = useCallback(
    (href: string) => {
      setOpen(false);
      router.push(href);
    },
    [router]
  );

  // ── Open / close keyboard shortcut (Ctrl+K / Cmd+K) ──
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  // ── Open via custom DOM event (from TopNav search button) ──
  useEffect(() => {
    const handler = () => setOpen(true);
    window.addEventListener("cmdpalette:open", handler);
    return () => window.removeEventListener("cmdpalette:open", handler);
  }, []);

  // ── Focus & reset on open ──
  useEffect(() => {
    if (open) {
      setQuery("");
      setContacts([]);
      setSequences([]);
      setSelectedIndex(0);
      // Defer focus to let the DOM mount
      const t = setTimeout(() => inputRef.current?.focus(), 30);
      return () => clearTimeout(t);
    }
  }, [open]);

  // ── Debounced search ──
  useEffect(() => {
    if (!query.trim()) {
      setContacts([]);
      setSequences([]);
      setSelectedIndex(0);
      return;
    }
    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        const [contactsRes, seqRes] = await Promise.all([
          crmApi.listContacts({ query: query.trim(), limit: 5 }),
          sequencesApi.listSequences(1, 50),
        ]);
        setContacts(contactsRes.items ?? []);
        const q = query.toLowerCase();
        setSequences(
          (seqRes.items ?? []).filter(
            (s) =>
              s.name.toLowerCase().includes(q) ||
              (s.description ?? "").toLowerCase().includes(q)
          )
        );
      } catch {
        // silent — search is best-effort
      } finally {
        setLoading(false);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [query]);

  // ── Build flat navigable items list ──
  const allItems = useMemo<NavItem[]>(() => {
    const pages = query.trim()
      ? PAGE_SHORTCUTS.filter((p) =>
          p.label.toLowerCase().includes(query.toLowerCase())
        )
      : PAGE_SHORTCUTS;

    const pageItems: NavItem[] = pages.map((p) => ({
      key: `page-${p.href}`,
      label: p.label,
      subtitle: p.href,
      icon: <p.Icon size={14} color="#666" />,
      action: () => navigate(p.href),
      section: query.trim() ? "Pages" : "Navigation",
    }));

    const contactItems: NavItem[] = contacts.map((c) => ({
      key: `contact-${c.id}`,
      label: `${c.first_name} ${c.last_name}`,
      subtitle: c.email,
      icon: <ContactAvatar contact={c} />,
      action: () => navigate("/crm"),
      section: "Contacts",
    }));

    const seqItems: NavItem[] = sequences.map((s) => ({
      key: `seq-${s.id}`,
      label: s.name,
      subtitle: `${s.step_count} étapes · ${s.status}`,
      icon: <Workflow size={14} color="#c88cff" />,
      action: () => navigate("/sequences"),
      section: "Séquences",
    }));

    return [...pageItems, ...contactItems, ...seqItems];
  }, [query, contacts, sequences, navigate]);

  // Reset selectedIndex when items change
  useEffect(() => {
    setSelectedIndex(0);
  }, [allItems.length]);

  // ── Keyboard navigation ──
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        return;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelectedIndex((i) => Math.min(i + 1, allItems.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelectedIndex((i) => Math.max(i - 1, 0));
      } else if (e.key === "Enter" && allItems[selectedIndex]) {
        e.preventDefault();
        allItems[selectedIndex].action();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, allItems, selectedIndex]);

  // Scroll selected item into view
  useEffect(() => {
    const el = listRef.current?.querySelector("[data-selected='true']");
    el?.scrollIntoView({ block: "nearest" });
  }, [selectedIndex]);

  if (!open) return null;

  // Group items by section for rendering
  const sections = allItems.reduce<{ label: string; items: NavItem[] }[]>(
    (acc, item) => {
      const last = acc[acc.length - 1];
      if (last && last.label === item.section) {
        last.items.push(item);
      } else {
        acc.push({ label: item.section, items: [item] });
      }
      return acc;
    },
    []
  );

  const noResults =
    query.trim() && !loading && allItems.length === 0;

  return (
    <>
      {/* ── Backdrop ── */}
      <div
        onClick={() => setOpen(false)}
        style={{
          position: "fixed",
          inset: 0,
          background: "rgba(0,0,0,0.72)",
          backdropFilter: "blur(4px)",
          zIndex: 1000,
        }}
      />

      {/* ── Modal ── */}
      <div
        style={{
          position: "fixed",
          top: "18%",
          left: "50%",
          transform: "translateX(-50%)",
          width: "min(580px, calc(100vw - 32px))",
          background: "#111",
          border: "1px solid rgba(255,255,255,0.1)",
          borderRadius: 14,
          boxShadow:
            "0 24px 64px rgba(0,0,0,0.85), 0 0 0 1px rgba(255,255,255,0.04)",
          zIndex: 1001,
          overflow: "hidden",
        }}
      >
        {/* Search input row */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            padding: "13px 16px",
            borderBottom: "1px solid rgba(255,255,255,0.07)",
          }}
        >
          <Search size={16} color="#555" style={{ flexShrink: 0 }} />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Rechercher contacts, séquences, pages…"
            style={{
              flex: 1,
              background: "none",
              border: "none",
              outline: "none",
              fontSize: 14,
              color: "#f5f5f5",
              caretColor: "#50b4ff",
            }}
          />
          {loading && (
            <span style={{ fontSize: 11, color: "#444", flexShrink: 0 }}>…</span>
          )}
          <kbd style={KBD}>ESC</kbd>
        </div>

        {/* Results list */}
        <div
          ref={listRef}
          style={{ maxHeight: 380, overflowY: "auto" }}
        >
          {noResults ? (
            <div
              style={{
                padding: "28px 16px",
                textAlign: "center",
                color: "#444",
                fontSize: 13,
              }}
            >
              Aucun résultat pour «{query}»
            </div>
          ) : (
            sections.map(({ label, items }) => (
              <ResultSection key={label} label={label}>
                {items.map((item) => {
                  const flatIndex = allItems.indexOf(item);
                  return (
                    <div key={item.key} data-selected={flatIndex === selectedIndex ? "true" : undefined}>
                      <ResultRow
                        icon={item.icon}
                        label={item.label}
                        subtitle={item.subtitle}
                        selected={flatIndex === selectedIndex}
                        onClick={item.action}
                      />
                    </div>
                  );
                })}
              </ResultSection>
            ))
          )}
        </div>

        {/* Footer hints */}
        <div
          style={{
            padding: "7px 16px",
            borderTop: "1px solid rgba(255,255,255,0.05)",
            display: "flex",
            gap: 14,
            alignItems: "center",
          }}
        >
          <span style={{ fontSize: 10, color: "#3a3a3a" }}>
            <kbd style={KBD}>↵</kbd> ouvrir
          </span>
          <span style={{ fontSize: 10, color: "#3a3a3a" }}>
            <kbd style={KBD}>↑↓</kbd> naviguer
          </span>
          <span style={{ fontSize: 10, color: "#3a3a3a" }}>
            <kbd style={KBD}>Ctrl</kbd>
            <kbd style={KBD}>K</kbd> fermer
          </span>
        </div>
      </div>
    </>
  );
}
