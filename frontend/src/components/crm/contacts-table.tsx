"use client";

import { Search, Plus, Pencil } from "lucide-react";
import { useState } from "react";
import { Spinner } from "@/components/ui/spinner";
import { useApiQuery } from "@/hooks/useApi";
import { crmApi } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { ContactDetailPanel } from "./contact-detail-panel";
import { ContactFormModal } from "./contact-form-modal";
import type { Contact, ContactStatus } from "@/types";

/* ── Status config — Venetian palette ─────────────────── */
const STATUS_CONFIG: Record<
  ContactStatus,
  { label: string; color: string; bg: string; border: string }
> = {
  active:   { label: "Actif",   color: "#00E87A", bg: "rgba(0,232,122,0.08)",  border: "rgba(0,232,122,0.3)" },
  customer: { label: "Client",  color: "#00E87A", bg: "rgba(0,232,122,0.08)",  border: "rgba(0,232,122,0.3)" },
  lead:     { label: "Lead",    color: "#FBBD23", bg: "rgba(251,189,35,0.08)", border: "rgba(251,189,35,0.3)" },
  inactive: { label: "Inactif", color: "#666666", bg: "rgba(85,85,85,0.06)",   border: "rgba(85,85,85,0.2)"  },
  churned:  { label: "Churné",  color: "#C00000", bg: "rgba(192,0,0,0.1)",     border: "rgba(192,0,0,0.35)" },
};

/* ── Helpers ───────────────────────────────────────────── */
const GLYPHS = ["✦", "◈", "◉", "⚜", "▲", "◎", "✧", "◆"];

function getGlyph(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
  return GLYPHS[Math.abs(hash) % GLYPHS.length];
}

function getInitials(first: string, last: string): string {
  return `${first.charAt(0)}${last.charAt(0)}`.toUpperCase();
}

/* ── Status badge ──────────────────────────────────────── */
function StatusBadge({ status }: { status: ContactStatus }) {
  const cfg = STATUS_CONFIG[status];
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded px-2 py-0.5 text-xs"
      style={{
        background: cfg.bg,
        color: cfg.color,
        border: `1px solid ${cfg.border}`,
        fontFamily: "var(--font-body)",
      }}
    >
      <span
        className="h-1.5 w-1.5 rounded-full flex-shrink-0"
        style={{ background: cfg.color, boxShadow: `0 0 5px ${cfg.color}` }}
      />
      {cfg.label}
    </span>
  );
}

/* ── Portrait card (featured) ──────────────────────────── */
function PortraitCard({ contact, onClick }: { contact: Contact; onClick: () => void }) {
  const initials = getInitials(contact.first_name, contact.last_name);
  const glyph = getGlyph(`${contact.first_name}${contact.last_name}`);

  return (
    <button
      className="tablette-marbre tablette-interactive text-left overflow-hidden w-full"
      style={{ padding: 0, cursor: "pointer", border: "none" }}
      onClick={onClick}
    >
      {/* Portrait zone */}
      <div
        style={{
          height: 90,
          background: "radial-gradient(ellipse at 50% 0%, #2A0000 0%, #050505 65%)",
          borderBottom: "1px solid var(--red-dark)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          position: "relative",
          overflow: "hidden",
        }}
      >
        {/* Halo de fond */}
        <div
          className="absolute inset-0"
          style={{ background: "radial-gradient(ellipse at 50% 0%, rgba(138,0,0,0.35), transparent 65%)" }}
        />
        {/* Médaillon */}
        <div
          style={{
            width: 54, height: 54, borderRadius: "50%", position: "relative", zIndex: 1,
            background: "radial-gradient(circle at 38% 32%, #3A0000 0%, #0A0000 60%)",
            border: "1.5px solid var(--red-dark)",
            boxShadow: "var(--glow-red), var(--inner-shadow-red)",
            display: "flex", flexDirection: "column",
            alignItems: "center", justifyContent: "center", gap: 1,
          }}
        >
          <span
            className="font-cinzel font-bold"
            style={{ color: "var(--white-spectral)", fontSize: "0.8rem", lineHeight: 1 }}
          >
            {initials}
          </span>
          <span style={{ color: "var(--red-doge)", fontSize: "0.5rem", lineHeight: 1 }}>{glyph}</span>
        </div>
      </div>

      {/* Info */}
      <div className="px-3 py-2.5">
        <p
          className="font-cinzel text-xs font-semibold truncate"
          style={{ color: "var(--white-spectral)" }}
        >
          {contact.first_name} {contact.last_name}
        </p>
        <p
          className="truncate mt-0.5"
          style={{ color: "var(--gray-silver)", fontFamily: "var(--font-body)", fontSize: "0.6rem" }}
        >
          {contact.email}
        </p>
        <p
          className="truncate mt-1"
          style={{ color: "var(--red-doge)", fontFamily: "var(--font-body)", fontSize: "0.6rem", letterSpacing: "0.04em" }}
        >
          {contact.job_title ?? "—"}
        </p>
      </div>
    </button>
  );
}

/* ── Main component ────────────────────────────────────── */
const PAGE_SIZE = 8;

export function ContactsTable() {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Contact | null>(null);
  const [focusSearch, setFocusSearch] = useState(false);
  const [page, setPage] = useState(1);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editContact, setEditContact] = useState<Contact | null>(null);

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
      <div
        className="tablette-marbre p-6 text-center text-sm"
        style={{ color: "var(--red-doge)" }}
      >
        ⚜ Erreur lors du chargement des contacts : {error.message}
      </div>
    );
  }

  const allContacts: Contact[] = data?.items ?? [];
  const filtered = query.trim()
    ? allContacts.filter((c) => {
        const q = query.toLowerCase();
        return (
          `${c.first_name} ${c.last_name}`.toLowerCase().includes(q) ||
          c.email.toLowerCase().includes(q) ||
          (c.job_title ?? "").toLowerCase().includes(q)
        );
      })
    : allContacts;

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const contacts = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  const featured = allContacts.slice(0, 5);

  return (
    <>
      <ContactDetailPanel
        contact={selected}
        onClose={() => setSelected(null)}
        onEdit={(c) => { setSelected(null); setEditContact(c); }}
      />

      {/* Modals CRUD */}
      {showCreateModal && (
        <ContactFormModal
          onClose={() => setShowCreateModal(false)}
        />
      )}
      {editContact && (
        <ContactFormModal
          contact={editContact}
          onClose={() => setEditContact(null)}
        />
      )}

      <div className="space-y-5">

        {/* ── Portraits en vedette ─────────────────────────── */}
        {featured.length > 0 && (
          <div
            className="grid gap-3"
            style={{ gridTemplateColumns: `repeat(${Math.min(featured.length, 5)}, 1fr)` }}
          >
            {featured.map((contact) => (
              <PortraitCard
                key={contact.id}
                contact={contact}
                onClick={() => setSelected(contact)}
              />
            ))}
          </div>
        )}

        {/* ── Tableau des contacts ─────────────────────────── */}
        <div className="tablette-marbre overflow-hidden" style={{ padding: 0 }}>

          {/* Toolbar */}
          <div
            className="flex items-center gap-3 px-5 py-3"
            style={{ borderBottom: "1px solid rgba(138,0,0,0.2)" }}
          >
            {/* Search */}
            <div
              className="flex items-center gap-2 flex-1 max-w-xs rounded px-3 py-1.5 transition-all duration-200"
              style={{
                background: "rgba(10,10,10,0.7)",
                border: focusSearch ? "1px solid var(--red-doge)" : "1px solid var(--red-dark)",
                boxShadow: focusSearch ? "var(--glow-red)" : "none",
              }}
            >
              <Search size={11} style={{ color: "var(--red-doge)", flexShrink: 0 }} />
              <input
                type="text"
                value={query}
                onChange={(e) => { setQuery(e.target.value); setPage(1); }}
                onFocus={() => setFocusSearch(true)}
                onBlur={() => setFocusSearch(false)}
                placeholder="Rechercher un contact…"
                className="flex-1 bg-transparent text-xs outline-none"
                style={{ color: "var(--white-spectral)", fontFamily: "var(--font-body)" }}
              />
            </div>
            <span
              className="ml-auto font-cinzel text-xs tracking-[0.1em]"
              style={{ color: "var(--gray-silver)" }}
            >
              {contacts.length} contact{contacts.length !== 1 ? "s" : ""}
            </span>
            {/* Bouton Nouveau contact */}
            <button
              onClick={() => setShowCreateModal(true)}
              className="font-cinzel flex items-center gap-1.5 rounded transition-all duration-150"
              style={{
                background: "rgba(138,0,0,0.25)",
                border: "1px solid var(--red-dark)",
                padding: "5px 14px",
                color: "var(--white-spectral)",
                cursor: "pointer",
                fontSize: "0.65rem",
                letterSpacing: "0.1em",
                textTransform: "uppercase",
                boxShadow: "var(--glow-red)",
              }}
              onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = "rgba(138,0,0,0.45)"; }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = "rgba(138,0,0,0.25)"; }}
            >
              <Plus size={11} />
              Nouveau contact
            </button>
          </div>

          {/* Empty state */}
          {contacts.length === 0 ? (
            <div className="p-12 text-center">
              <p
                className="font-cinzel text-xs tracking-[0.2em] uppercase"
                style={{ color: "var(--gray-silver)" }}
              >
                {query ? "Aucun contact ne correspond à la recherche." : "Aucun contact trouvé."}
              </p>
            </div>
          ) : (
            <table className="w-full">
              <thead style={{ borderBottom: "1px solid rgba(138,0,0,0.2)" }}>
                <tr>
                  {["Contact", "Email", "Poste", "Statut", "Créé le", ""].map((h, i) => (
                    <th
                      key={i}
                      className="px-5 py-3 text-left font-cinzel text-xs tracking-[0.15em] uppercase"
                      style={{ color: "var(--red-doge)" }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {contacts.map((contact, i) => {
                  const initials = getInitials(contact.first_name, contact.last_name);
                  const glyph = getGlyph(`${contact.first_name}${contact.last_name}`);
                  return (
                    <tr
                      key={contact.id}
                      className="transition-all duration-150"
                      style={{
                        borderBottom: i < contacts.length - 1 ? "1px solid rgba(138,0,0,0.1)" : "none",
                        cursor: "pointer",
                      }}
                      onClick={() => setSelected(contact)}
                      onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(138,0,0,0.06)"; }}
                      onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
                    >
                      {/* Contact */}
                      <td className="px-5 py-3">
                        <div className="flex items-center gap-3">
                          <div
                            style={{
                              width: 30, height: 30, borderRadius: "50%", flexShrink: 0,
                              background: "radial-gradient(circle, #1A0000, #050505)",
                              border: "1px solid var(--red-dark)",
                              boxShadow: "var(--glow-red)",
                              display: "flex", flexDirection: "column",
                              alignItems: "center", justifyContent: "center", gap: 0,
                            }}
                          >
                            <span
                              className="font-cinzel font-bold"
                              style={{ color: "var(--white-spectral)", fontSize: "0.55rem", lineHeight: 1.2 }}
                            >
                              {initials}
                            </span>
                            <span style={{ color: "var(--red-doge)", fontSize: "0.4rem", lineHeight: 1 }}>
                              {glyph}
                            </span>
                          </div>
                          <span
                            className="font-cinzel text-xs font-semibold"
                            style={{ color: "var(--white-spectral)" }}
                          >
                            {contact.first_name} {contact.last_name}
                          </span>
                        </div>
                      </td>

                      <td
                        className="px-5 py-3 text-xs"
                        style={{ color: "var(--gray-silver)", fontFamily: "var(--font-body)" }}
                      >
                        {contact.email}
                      </td>

                      <td
                        className="px-5 py-3 text-xs"
                        style={{ color: "var(--gray-silver)", fontFamily: "var(--font-body)" }}
                      >
                        {contact.job_title ?? "—"}
                      </td>

                      <td className="px-5 py-3">
                        <StatusBadge status={contact.status} />
                      </td>

                      <td
                        className="px-5 py-3 text-xs"
                        style={{
                          color: "var(--red-dark)",
                          fontFamily: "var(--font-mono)",
                          fontSize: "0.65rem",
                          letterSpacing: "0.05em",
                        }}
                      >
                        {formatDate(contact.created_at)}
                      </td>

                      {/* Actions */}
                      <td className="px-3 py-3">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setEditContact(contact);
                          }}
                          title="Modifier"
                          style={{
                            background: "transparent",
                            border: "1px solid rgba(138,0,0,0.25)",
                            borderRadius: 4,
                            padding: "4px 6px",
                            cursor: "pointer",
                            color: "var(--gray-silver)",
                            display: "flex",
                            alignItems: "center",
                          }}
                          onMouseEnter={(e) => {
                            const btn = e.currentTarget as HTMLButtonElement;
                            btn.style.color = "var(--red-doge)";
                            btn.style.borderColor = "var(--red-doge)";
                          }}
                          onMouseLeave={(e) => {
                            const btn = e.currentTarget as HTMLButtonElement;
                            btn.style.color = "var(--gray-silver)";
                            btn.style.borderColor = "rgba(138,0,0,0.25)";
                          }}
                        >
                          <Pencil size={11} />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}

          {/* ── Pagination ─────────────────────────────────── */}
          {totalPages > 1 && (
            <div
              className="flex items-center justify-between px-5 py-3"
              style={{ borderTop: "1px solid rgba(138,0,0,0.2)" }}
            >
              <span
                className="font-cinzel text-xs tracking-[0.08em]"
                style={{ color: "var(--gray-silver)" }}
              >
                Page {currentPage} / {totalPages}
              </span>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setPage(1)}
                  disabled={currentPage === 1}
                  className="px-2 py-1 rounded text-xs transition-all duration-150 disabled:opacity-30"
                  style={{
                    fontFamily: "var(--font-mono)",
                    color: currentPage === 1 ? "var(--gray-silver)" : "var(--red-doge)",
                    border: "1px solid var(--red-dark)",
                    background: "transparent",
                    cursor: currentPage === 1 ? "default" : "pointer",
                  }}
                >
                  «
                </button>
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={currentPage === 1}
                  className="px-2 py-1 rounded text-xs transition-all duration-150 disabled:opacity-30"
                  style={{
                    fontFamily: "var(--font-mono)",
                    color: currentPage === 1 ? "var(--gray-silver)" : "var(--red-doge)",
                    border: "1px solid var(--red-dark)",
                    background: "transparent",
                    cursor: currentPage === 1 ? "default" : "pointer",
                  }}
                >
                  ‹
                </button>

                {Array.from({ length: totalPages }, (_, i) => i + 1)
                  .filter((p) => p === 1 || p === totalPages || Math.abs(p - currentPage) <= 1)
                  .reduce<(number | "…")[]>((acc, p, idx, arr) => {
                    if (idx > 0 && p - (arr[idx - 1] as number) > 1) acc.push("…");
                    acc.push(p);
                    return acc;
                  }, [])
                  .map((item, idx) =>
                    item === "…" ? (
                      <span
                        key={`ellipsis-${idx}`}
                        className="px-1 text-xs"
                        style={{ color: "var(--gray-silver)", fontFamily: "var(--font-mono)" }}
                      >
                        …
                      </span>
                    ) : (
                      <button
                        key={item}
                        onClick={() => setPage(item as number)}
                        className="w-7 h-7 rounded text-xs font-cinzel transition-all duration-150"
                        style={{
                          background: currentPage === item ? "rgba(138,0,0,0.3)" : "transparent",
                          color: currentPage === item ? "var(--white-spectral)" : "var(--gray-silver)",
                          border: currentPage === item ? "1px solid var(--red-doge)" : "1px solid var(--red-dark)",
                          boxShadow: currentPage === item ? "var(--glow-red)" : "none",
                          cursor: "pointer",
                        }}
                      >
                        {item}
                      </button>
                    )
                  )}

                <button
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={currentPage === totalPages}
                  className="px-2 py-1 rounded text-xs transition-all duration-150 disabled:opacity-30"
                  style={{
                    fontFamily: "var(--font-mono)",
                    color: currentPage === totalPages ? "var(--gray-silver)" : "var(--red-doge)",
                    border: "1px solid var(--red-dark)",
                    background: "transparent",
                    cursor: currentPage === totalPages ? "default" : "pointer",
                  }}
                >
                  ›
                </button>
                <button
                  onClick={() => setPage(totalPages)}
                  disabled={currentPage === totalPages}
                  className="px-2 py-1 rounded text-xs transition-all duration-150 disabled:opacity-30"
                  style={{
                    fontFamily: "var(--font-mono)",
                    color: currentPage === totalPages ? "var(--gray-silver)" : "var(--red-doge)",
                    border: "1px solid var(--red-dark)",
                    background: "transparent",
                    cursor: currentPage === totalPages ? "default" : "pointer",
                  }}
                >
                  »
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

