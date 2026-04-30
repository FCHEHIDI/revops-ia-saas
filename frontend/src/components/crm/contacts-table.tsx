"use client";

import { Search } from "lucide-react";
import { useState } from "react";
import { Spinner } from "@/components/ui/spinner";
import { useApiQuery } from "@/hooks/useApi";
import { crmApi } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import type { Contact, ContactStatus } from "@/types";

/* ── Status config ─────────────────────────────────────── */
const STATUS_CONFIG: Record<
  ContactStatus,
  { label: string; dot: string; bg: string; text: string; border: string }
> = {
  active:   { label: "Actif",   dot: "#00ff88", bg: "rgba(0,255,136,0.08)",  text: "#00ff88", border: "rgba(0,255,136,0.25)" },
  customer: { label: "Client",  dot: "#00ff88", bg: "rgba(0,255,136,0.08)",  text: "#00ff88", border: "rgba(0,255,136,0.25)" },
  lead:     { label: "Lead",    dot: "#fbbf24", bg: "rgba(251,191,36,0.08)", text: "#fbbf24", border: "rgba(251,191,36,0.25)" },
  inactive: { label: "Inactif", dot: "#555555", bg: "rgba(85,85,85,0.08)",   text: "#666666", border: "rgba(85,85,85,0.25)"  },
  churned:  { label: "Churné",  dot: "#ff0000", bg: "rgba(255,0,0,0.08)",    text: "#ff0000", border: "rgba(255,0,0,0.25)"  },
};

/* ── Avatar color palette ──────────────────────────────── */
const AVATAR_COLORS = [
  "#4ade80", "#fbbf24", "#ff0000", "#f472b6", "#38bdf8",
  "#a78bfa", "#fb923c", "#34d399",
];
function getAvatarColor(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length];
}
function getInitials(first: string, last: string): string {
  return `${first.charAt(0)}${last.charAt(0)}`.toUpperCase();
}

/* ── Status badge ──────────────────────────────────────── */
function StatusBadge({ status }: { status: ContactStatus }) {
  const cfg = STATUS_CONFIG[status];
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded px-2 py-0.5 text-xs font-medium"
      style={{ background: cfg.bg, color: cfg.text, border: `1px solid ${cfg.border}` }}
    >
      <span
        className="h-1.5 w-1.5 rounded-full flex-shrink-0"
        style={{
          background: cfg.dot,
          boxShadow: status !== "inactive" ? `0 0 6px ${cfg.dot}` : undefined,
        }}
      />
      {cfg.label}
    </span>
  );
}

/* ── Main component ────────────────────────────────────── */
export function ContactsTable() {
  const [query, setQuery] = useState("");

  const { data, isLoading, error } = useApiQuery(
    ["contacts"],
    () => crmApi.listContacts({ page: 1, limit: 50 })
  );

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Spinner size="lg" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg p-6 text-center text-sm"
        style={{ border: "1px solid rgba(255,0,0,0.3)", background: "rgba(74,0,0,0.3)", color: "var(--accent-red)" }}>
        Erreur lors du chargement des contacts : {error.message}
      </div>
    );
  }

  const allContacts: Contact[] = data?.items ?? [];
  const contacts = query.trim()
    ? allContacts.filter((c) => {
        const q = query.toLowerCase();
        return (
          `${c.first_name} ${c.last_name}`.toLowerCase().includes(q) ||
          c.email.toLowerCase().includes(q) ||
          (c.job_title ?? "").toLowerCase().includes(q)
        );
      })
    : allContacts;

  return (
    <div
      className="overflow-hidden rounded-xl"
      style={{ border: "1px solid var(--border-default)" }}
    >
      {/* Toolbar */}
      <div
        className="flex items-center gap-3 px-4 py-3"
        style={{ background: "var(--bg-surface)", borderBottom: "1px solid var(--border-subtle)" }}
      >
        <div
          className="flex items-center gap-2 flex-1 max-w-xs rounded-lg px-3 py-1.5"
          style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-default)" }}
        >
          <Search size={12} style={{ color: "var(--text-muted)", flexShrink: 0 }} />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Rechercher un contact…"
            className="flex-1 bg-transparent text-xs outline-none"
            style={{ color: "var(--text-primary)" }}
          />
        </div>
        <span className="ml-auto text-xs" style={{ color: "var(--text-muted)" }}>
          {contacts.length} résultat{contacts.length !== 1 ? "s" : ""}
        </span>
      </div>

      {contacts.length === 0 ? (
        <div
          className="p-12 text-center text-sm"
          style={{ background: "var(--bg-surface)", color: "var(--text-secondary)" }}
        >
          {query ? "Aucun contact ne correspond à la recherche." : "Aucun contact trouvé."}
        </div>
      ) : (
        <table className="w-full text-sm">
          <thead style={{ background: "var(--bg-surface)", borderBottom: "1px solid var(--border-subtle)" }}>
            <tr>
              {["Contact", "Email", "Poste", "Statut", "Créé le"].map((h) => (
                <th
                  key={h}
                  className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-widest"
                  style={{ color: "var(--text-muted)" }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {contacts.map((contact) => {
              const initials = getInitials(contact.first_name, contact.last_name);
              const color = getAvatarColor(`${contact.first_name}${contact.last_name}`);
              return (
                <tr
                  key={contact.id}
                  className="group transition-colors"
                  style={{ borderBottom: "1px solid var(--border-subtle)", background: "var(--bg-surface)" }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = "var(--bg-elevated)")}
                  onMouseLeave={(e) => (e.currentTarget.style.background = "var(--bg-surface)")}
                >
                  {/* Contact name + avatar */}
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <div
                        className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg text-xs font-bold"
                        style={{ background: "var(--bg-elevated)", color, border: `1px solid ${color}30` }}
                      >
                        {initials}
                      </div>
                      <span className="font-medium" style={{ color: "var(--text-primary)" }}>
                        {contact.first_name} {contact.last_name}
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-xs" style={{ color: "var(--text-secondary)" }}>
                    {contact.email}
                  </td>
                  <td className="px-4 py-3 text-xs" style={{ color: "var(--text-secondary)" }}>
                    {contact.job_title ?? "—"}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={contact.status} />
                  </td>
                  <td className="px-4 py-3 text-xs" style={{ color: "var(--text-muted)" }}>
                    {formatDate(contact.created_at)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
