"use client";

import { Users } from "lucide-react";
import { Spinner } from "@/components/ui/spinner";
import { useApiQuery } from "@/hooks/useApi";
import { crmApi } from "@/lib/api";
import type { ContactStatus } from "@/types";

/* ── Segment definitions ─────────────────────────────────── */
const SEGMENT_CONFIG: Record<
  ContactStatus,
  {
    label: string;
    description: string;
    color: string;
    bg: string;
    border: string;
    glow: string;
    glyph: string;
  }
> = {
  customer: {
    label: "Clients",
    description: "Comptes actifs avec contrat",
    color: "#00E87A",
    bg: "rgba(0,232,122,0.06)",
    border: "rgba(0,232,122,0.2)",
    glow: "rgba(0,232,122,0.15)",
    glyph: "◈",
  },
  active: {
    label: "Actifs",
    description: "Contacts engagés récemment",
    color: "#2979FF",
    bg: "rgba(41,121,255,0.06)",
    border: "rgba(41,121,255,0.2)",
    glow: "rgba(41,121,255,0.12)",
    glyph: "✦",
  },
  lead: {
    label: "Leads",
    description: "Prospects en cours de qualification",
    color: "#FBBD23",
    bg: "rgba(251,189,35,0.06)",
    border: "rgba(251,189,35,0.2)",
    glow: "rgba(251,189,35,0.12)",
    glyph: "◎",
  },
  inactive: {
    label: "Inactifs",
    description: "Sans interaction depuis 90 jours",
    color: "#666666",
    bg: "rgba(85,85,85,0.04)",
    border: "rgba(85,85,85,0.15)",
    glow: "transparent",
    glyph: "▲",
  },
  churned: {
    label: "Churnés",
    description: "Contrat résilié ou perdu",
    color: "#C00000",
    bg: "rgba(192,0,0,0.06)",
    border: "rgba(192,0,0,0.2)",
    glow: "rgba(192,0,0,0.12)",
    glyph: "⚜",
  },
};

const STATUS_ORDER: ContactStatus[] = ["customer", "active", "lead", "inactive", "churned"];

/* ── Main component ──────────────────────────────────────── */
export function SegmentsTable() {
  // Fetch a large page to count across all segments
  const { data, isLoading, error } = useApiQuery(
    ["contacts-segments"],
    () => crmApi.listContacts({ limit: 1000 }),
  );

  const contacts = data?.items ?? [];
  const total    = contacts.length;

  // Group by status
  const counts = contacts.reduce<Partial<Record<ContactStatus, number>>>((acc, c) => {
    acc[c.status] = (acc[c.status] ?? 0) + 1;
    return acc;
  }, {});

  const activeSegments = STATUS_ORDER.filter((s) => (counts[s] ?? 0) > 0).length;

  return (
    <div>
      {isLoading && (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      )}

      {error && !isLoading && (
        <div
          className="tablette-marbre flex items-center justify-center"
          style={{ minHeight: 200 }}
        >
          <p className="font-mono-geist text-xs" style={{ color: "var(--text-muted)" }}>
            Impossible de charger les segments
          </p>
        </div>
      )}

      {!isLoading && !error && (
        <>
          {/* Header */}
          <div className="flex items-center justify-between mb-6">
            <div>
              <h2
                className="font-cinzel text-sm font-semibold"
                style={{ color: "var(--white-spectral)" }}
              >
                Segmentation contacts
              </h2>
              <p
                className="font-mono-geist text-xs mt-0.5"
                style={{ color: "var(--text-muted)" }}
              >
                {total} contact{total !== 1 ? "s" : ""} répartis en{" "}
                {activeSegments} segment{activeSegments !== 1 ? "s" : ""}
              </p>
            </div>
            <div className="flex items-center gap-1.5">
              <Users size={12} style={{ color: "var(--text-muted)" }} />
              <span
                className="font-mono-geist text-xs font-medium"
                style={{ color: "var(--text-secondary)" }}
              >
                {total} total
              </span>
            </div>
          </div>

          {/* Segment cards */}
          <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
            {STATUS_ORDER.map((status) => {
              const cfg   = SEGMENT_CONFIG[status];
              const count = counts[status] ?? 0;
              const pct   = total > 0 ? Math.round((count / total) * 100) : 0;

              return (
                <div
                  key={status}
                  className="rounded-xl p-4 transition-all duration-200"
                  style={{
                    background: cfg.bg,
                    border: `1px solid ${cfg.border}`,
                    boxShadow: count > 0 ? `0 0 20px ${cfg.glow}` : "none",
                  }}
                >
                  {/* Top row */}
                  <div className="flex items-start justify-between mb-3">
                    <span className="font-cinzel text-lg" style={{ color: cfg.color }}>
                      {cfg.glyph}
                    </span>
                    <span
                      className="font-mono-geist text-xs px-2 py-0.5 rounded"
                      style={{
                        background: `${cfg.color}18`,
                        color: cfg.color,
                        border: `1px solid ${cfg.border}`,
                      }}
                    >
                      {pct}%
                    </span>
                  </div>

                  {/* Count */}
                  <p
                    className="font-cinzel text-3xl font-bold mb-0.5"
                    style={{ color: cfg.color }}
                  >
                    {count}
                  </p>

                  <p
                    className="font-cinzel text-xs font-semibold tracking-wide mb-1"
                    style={{ color: "var(--white-spectral)" }}
                  >
                    {cfg.label}
                  </p>

                  <p
                    className="text-xs"
                    style={{ color: "var(--text-muted)", fontFamily: "var(--font-body)" }}
                  >
                    {cfg.description}
                  </p>

                  {/* Progress bar */}
                  <div
                    className="mt-3 h-0.5 rounded-full overflow-hidden"
                    style={{ background: "var(--border-subtle)" }}
                  >
                    <div
                      className="h-full rounded-full transition-all duration-500"
                      style={{
                        width: `${pct}%`,
                        background: cfg.color,
                        boxShadow: `0 0 6px ${cfg.color}`,
                      }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
