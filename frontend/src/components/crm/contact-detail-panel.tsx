"use client";

import { useEffect, useState } from "react";
import {
  X, Mail, Phone, Building2, Briefcase,
  Calendar, DollarSign, TrendingUp, Pencil, Trash2,
} from "lucide-react";
import { useApiQuery } from "@/hooks/useApi";
import { crmApi } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import type { Contact, ContactStatus, DealStage } from "@/types";

/* ── Config ─────────────────────────────────────────────── */

const STATUS_CFG: Record<ContactStatus, { label: string; color: string; bg: string; border: string }> = {
  active:   { label: "Actif",   color: "#00ff88", bg: "rgba(0,255,136,0.1)",  border: "rgba(0,255,136,0.3)"  },
  customer: { label: "Client",  color: "#50b4ff", bg: "rgba(80,180,255,0.1)", border: "rgba(80,180,255,0.3)" },
  lead:     { label: "Lead",    color: "#fbbf24", bg: "rgba(251,191,36,0.1)", border: "rgba(251,191,36,0.3)" },
  inactive: { label: "Inactif", color: "#666666", bg: "rgba(85,85,85,0.1)",   border: "rgba(85,85,85,0.3)"   },
  churned:  { label: "Churné",  color: "#ff5050", bg: "rgba(255,80,80,0.1)",  border: "rgba(255,80,80,0.3)"  },
};

const STAGE_CFG: Record<DealStage, { label: string; color: string }> = {
  prospecting:   { label: "Prospection",   color: "#999999" },
  qualification: { label: "Qualification", color: "#fbbf24" },
  proposal:      { label: "Proposition",   color: "#50b4ff" },
  negotiation:   { label: "Négociation",   color: "#c88cff" },
  closing:       { label: "Closing",       color: "#ff8c00" },
  won:           { label: "Gagné",         color: "#00ff88" },
  lost:          { label: "Perdu",         color: "#ff5050" },
};

const AVATAR_COLORS = ["#4ade80", "#fbbf24", "#ff5050", "#f472b6", "#38bdf8", "#a78bfa", "#fb923c", "#34d399"];

function getAvatarColor(name: string): string {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = name.charCodeAt(i) + ((h << 5) - h);
  return AVATAR_COLORS[Math.abs(h) % AVATAR_COLORS.length];
}

function getInitials(first: string, last: string): string {
  return `${first.charAt(0)}${last.charAt(0)}`.toUpperCase();
}

function fmtEur(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(0)} k€` : `${n} €`;
}

/* ── Sub-components ─────────────────────────────────────── */

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <p style={{
        fontSize: 11, fontWeight: 600, color: "var(--text-muted)",
        textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 10,
      }}>
        {title}
      </p>
      <div style={{
        background: "var(--bg-elevated)", borderRadius: 10,
        border: "1px solid var(--border-subtle)", padding: "12px 14px",
        display: "flex", flexDirection: "column", gap: 10,
      }}>
        {children}
      </div>
    </div>
  );
}

function InfoRow({
  icon, label, value, badge,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  badge?: string;
}) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <span style={{ color: "var(--text-muted)", flexShrink: 0, display: "flex" }}>{icon}</span>
      <span style={{ fontSize: 12, color: "var(--text-secondary)", flexShrink: 0, width: 96 }}>{label}</span>
      <span style={{
        fontSize: 12, color: "var(--text-primary)", fontWeight: 500,
        flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
      }}>
        {value}
      </span>
      {badge && (
        <span style={{
          fontSize: 10, padding: "1px 6px", borderRadius: 4, flexShrink: 0,
          background: "rgba(80,180,255,0.1)", color: "#50b4ff", border: "1px solid rgba(80,180,255,0.2)",
        }}>
          {badge}
        </span>
      )}
    </div>
  );
}

function Timeline({ contact }: { contact: Contact }) {
  const events: { date: string; label: string; color: string }[] = [
    { date: contact.created_at, label: "Contact créé", color: "#50b4ff" },
  ];

  if (contact.status === "customer") {
    events.push({ date: contact.updated_at ?? contact.created_at, label: "Converti en client", color: "#00ff88" });
  }
  if (contact.status === "churned") {
    events.push({ date: contact.updated_at ?? contact.created_at, label: "Marqué comme churné", color: "#ff5050" });
  }
  if (contact.status === "inactive") {
    events.push({ date: contact.updated_at ?? contact.created_at, label: "Passé inactif", color: "#666666" });
  }

  events.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {events.map((ev, i) => (
        <div key={i} style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
          <div style={{ flexShrink: 0, marginTop: 4 }}>
            <div style={{
              width: 8, height: 8, borderRadius: "50%",
              background: ev.color, boxShadow: `0 0 6px ${ev.color}80`,
            }} />
          </div>
          <div>
            <p style={{ fontSize: 12, color: "var(--text-primary)", marginBottom: 2 }}>{ev.label}</p>
            <p style={{ fontSize: 11, color: "var(--text-muted)" }}>{formatDate(ev.date)}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

/* ── Main component ─────────────────────────────────────── */

interface Props {
  contact: Contact | null;
  onClose: () => void;
  onEdit?: (contact: Contact) => void;
  onDelete?: (contact: Contact) => void;
}

export function ContactDetailPanel({ contact, onClose, onEdit, onDelete }: Props) {
  const [confirmDelete, setConfirmDelete] = useState(false);

  // Close on Escape
  useEffect(() => {
    if (!contact) return;
    setConfirmDelete(false);
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [contact, onClose]);

  // Fetch account
  const { data: account } = useApiQuery(
    ["account", contact?.account_id ?? "skip"],
    () => crmApi.getAccount(contact!.account_id!),
    { enabled: !!contact?.account_id }
  );

  // Fetch deals — filter client-side by contact_id
  const { data: dealsData } = useApiQuery(
    ["deals-panel"],
    () => crmApi.listDeals({ page: 1, limit: 100 }),
    { enabled: !!contact }
  );
  const contactDeals = dealsData?.items.filter((d) => d.contact_id === contact?.id) ?? [];

  const open = !!contact;
  const color = contact ? getAvatarColor(`${contact.first_name}${contact.last_name}`) : "#999";
  const initials = contact ? getInitials(contact.first_name, contact.last_name) : "";
  const sc = contact ? STATUS_CFG[contact.status] : null;

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{
          position: "fixed", inset: 0, zIndex: 40,
          background: "rgba(0,0,0,0.55)",
          opacity: open ? 1 : 0,
          pointerEvents: open ? "auto" : "none",
          transition: "opacity 200ms ease",
        }}
      />

      {/* Slide-over panel */}
      <div
        style={{
          position: "fixed", top: 0, right: 0, bottom: 0,
          width: "min(480px, 100vw)", zIndex: 50,
          background: "var(--bg-surface)",
          borderLeft: "1px solid var(--border-default)",
          display: "flex", flexDirection: "column",
          transform: open ? "translateX(0)" : "translateX(100%)",
          transition: "transform 260ms cubic-bezier(0.4, 0, 0.2, 1)",
          overflow: "hidden",
        }}
      >
        {contact && (
          <>
            {/* ── Header ── */}
            <div style={{
              padding: "20px 24px 16px",
              borderBottom: "1px solid var(--border-subtle)",
              flexShrink: 0,
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 14 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  {/* Avatar */}
                  <div style={{
                    width: 48, height: 48, borderRadius: 12, flexShrink: 0,
                    display: "flex", alignItems: "center", justifyContent: "center",
                    background: "var(--bg-elevated)", color, border: `1px solid ${color}40`,
                    fontSize: 16, fontWeight: 700,
                  }}>
                    {initials}
                  </div>
                  <div>
                    <p style={{ fontSize: 16, fontWeight: 600, color: "var(--text-primary)", marginBottom: 5 }}>
                      {contact.first_name} {contact.last_name}
                    </p>
                    {sc && (
                      <span style={{
                        fontSize: 11, fontWeight: 500, padding: "2px 8px", borderRadius: 4,
                        background: sc.bg, color: sc.color, border: `1px solid ${sc.border}`,
                      }}>
                        {sc.label}
                      </span>
                    )}
                  </div>
                </div>

                {/* Close */}
                <button
                  onClick={onClose}
                  style={{
                    width: 28, height: 28, borderRadius: 6, flexShrink: 0,
                    border: "1px solid var(--border-default)", background: "var(--bg-elevated)",
                    display: "flex", alignItems: "center", justifyContent: "center",
                    cursor: "pointer", color: "var(--text-muted)",
                  }}
                >
                  <X size={14} />
                </button>
              </div>

              {/* Quick actions */}
              <div style={{ display: "flex", gap: 8 }}>
                <a
                  href={`mailto:${contact.email}`}
                  style={{
                    display: "flex", alignItems: "center", gap: 6,
                    padding: "6px 12px", borderRadius: 6, fontSize: 12, fontWeight: 500,
                    background: "rgba(80,180,255,0.1)", color: "#50b4ff",
                    border: "1px solid rgba(80,180,255,0.3)", textDecoration: "none",
                  }}
                >
                  <Mail size={12} /> Email
                </a>
                {contact.phone && (
                  <a
                    href={`tel:${contact.phone}`}
                    style={{
                      display: "flex", alignItems: "center", gap: 6,
                      padding: "6px 12px", borderRadius: 6, fontSize: 12, fontWeight: 500,
                      background: "rgba(120,255,160,0.1)", color: "#78ffa0",
                      border: "1px solid rgba(120,255,160,0.3)", textDecoration: "none",
                    }}
                  >
                    <Phone size={12} /> Appel
                  </a>
                )}
                {onEdit && (
                  <button
                    onClick={() => onEdit(contact)}
                    style={{
                      display: "flex", alignItems: "center", gap: 6,
                      padding: "6px 12px", borderRadius: 6, fontSize: 12, fontWeight: 500,
                      background: "rgba(138,0,0,0.12)", color: "var(--red-doge)",
                      border: "1px solid rgba(138,0,0,0.3)", cursor: "pointer",
                    }}
                  >
                    <Pencil size={12} /> Modifier
                  </button>
                )}
                {onDelete && (
                  confirmDelete ? (
                    <button
                      onClick={() => { onDelete(contact); setConfirmDelete(false); onClose(); }}
                      style={{
                        display: "flex", alignItems: "center", gap: 6,
                        padding: "6px 12px", borderRadius: 6, fontSize: 12, fontWeight: 500,
                        background: "rgba(192,0,0,0.25)", color: "#ff5050",
                        border: "1px solid #ff5050", cursor: "pointer",
                      }}
                    >
                      <Trash2 size={12} /> Confirmer
                    </button>
                  ) : (
                    <button
                      onClick={() => setConfirmDelete(true)}
                      style={{
                        display: "flex", alignItems: "center", gap: 6,
                        padding: "6px 12px", borderRadius: 6, fontSize: 12, fontWeight: 500,
                        background: "transparent", color: "var(--text-muted)",
                        border: "1px solid var(--border-subtle)", cursor: "pointer",
                      }}
                    >
                      <Trash2 size={12} /> Supprimer
                    </button>
                  )
                )}
              </div>
            </div>

            {/* ── Scrollable body ── */}
            <div style={{
              flex: 1, overflowY: "auto", padding: "20px 24px",
              display: "flex", flexDirection: "column", gap: 20,
            }}>
              {/* Informations */}
              <Section title="Informations">
                <InfoRow icon={<Mail size={13} />} label="Email" value={contact.email} />
                {contact.phone && <InfoRow icon={<Phone size={13} />} label="Téléphone" value={contact.phone} />}
                {contact.job_title && <InfoRow icon={<Briefcase size={13} />} label="Poste" value={contact.job_title} />}
                {account && (
                  <InfoRow
                    icon={<Building2 size={13} />}
                    label="Compte"
                    value={account.name}
                    badge={account.industry ?? undefined}
                  />
                )}
                <InfoRow icon={<Calendar size={13} />} label="Créé le" value={formatDate(contact.created_at)} />
                {contact.updated_at && (
                  <InfoRow icon={<Calendar size={13} />} label="Mis à jour" value={formatDate(contact.updated_at)} />
                )}
              </Section>

              {/* Account details (si ARR ou taille dispo) */}
              {account && (account.arr != null || account.size || account.domain) && (
                <Section title="Compte associé">
                  {account.domain && (
                    <InfoRow icon={<Building2 size={13} />} label="Domaine" value={account.domain} />
                  )}
                  {account.size && (
                    <InfoRow icon={<TrendingUp size={13} />} label="Taille" value={account.size} />
                  )}
                  {account.arr != null && (
                    <InfoRow icon={<DollarSign size={13} />} label="ARR" value={fmtEur(account.arr)} />
                  )}
                </Section>
              )}

              {/* Deals */}
              <Section title={`Deals${contactDeals.length > 0 ? ` (${contactDeals.length})` : ""}`}>
                {contactDeals.length === 0 ? (
                  <p style={{ fontSize: 12, color: "var(--text-muted)", fontStyle: "italic" }}>
                    Aucun deal associé à ce contact.
                  </p>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {contactDeals.map((deal) => {
                      const dc = STAGE_CFG[deal.stage] ?? { label: deal.stage ?? "—", color: "#888888" };
                      return (
                        <div
                          key={deal.id}
                          style={{
                            padding: "10px 12px", borderRadius: 8,
                            background: "var(--bg-surface)", border: "1px solid var(--border-subtle)",
                            display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8,
                          }}
                        >
                          <div style={{ minWidth: 0 }}>
                            <p style={{
                              fontSize: 13, fontWeight: 500, color: "var(--text-primary)",
                              marginBottom: 3, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                            }}>
                              {deal.title}
                            </p>
                            <span style={{ fontSize: 11, fontWeight: 500, color: dc.color }}>{dc.label}</span>
                          </div>
                          {deal.amount != null && (
                            <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", flexShrink: 0 }}>
                              {fmtEur(deal.amount)}
                            </span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </Section>

              {/* Activity */}
              <Section title="Activité récente">
                <Timeline contact={contact} />
              </Section>
            </div>
          </>
        )}
      </div>
    </>
  );
}
