"use client";

import { useState } from "react";
import { TrendingUp, Filter, DollarSign } from "lucide-react";
import { Spinner } from "@/components/ui/spinner";
import { useApiQuery } from "@/hooks/useApi";
import { crmApi } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import type { Deal, DealStage } from "@/types";

/* ── Stage palette ───────────────────────────────────────── */
const STAGE_CONFIG: Record<
  DealStage,
  { label: string; color: string; bg: string; border: string }
> = {
  prospecting:   { label: "Prospection",   color: "#9B9B9B", bg: "rgba(155,155,155,0.08)", border: "rgba(155,155,155,0.22)" },
  qualification: { label: "Qualification", color: "#2979FF", bg: "rgba(41,121,255,0.08)",  border: "rgba(41,121,255,0.22)"  },
  proposal:      { label: "Proposition",   color: "#FBBD23", bg: "rgba(251,189,35,0.08)",  border: "rgba(251,189,35,0.22)"  },
  negotiation:   { label: "Négociation",   color: "#C07000", bg: "rgba(192,112,0,0.10)",   border: "rgba(192,112,0,0.28)"   },
  closing:       { label: "Closing",       color: "#FF6B00", bg: "rgba(255,107,0,0.10)",   border: "rgba(255,107,0,0.28)"   },
  won:           { label: "Gagné",         color: "#00E87A", bg: "rgba(0,232,122,0.10)",   border: "rgba(0,232,122,0.28)"   },
  lost:          { label: "Perdu",         color: "#C00000", bg: "rgba(192,0,0,0.10)",     border: "rgba(192,0,0,0.28)"     },
};

const FILTER_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "",              label: "Tous" },
  { value: "prospecting",   label: "Prospection" },
  { value: "qualification", label: "Qualification" },
  { value: "proposal",      label: "Proposition" },
  { value: "negotiation",   label: "Négociation" },
  { value: "closing",       label: "Closing" },
  { value: "won",           label: "Gagnés" },
  { value: "lost",          label: "Perdus" },
];

function fmtAmount(amount?: number, currency = "EUR"): string {
  if (!amount) return "—";
  return new Intl.NumberFormat("fr-FR", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(amount);
}

function StageBadge({ stage }: { stage: DealStage }) {
  const cfg = STAGE_CONFIG[stage] ?? {
    label: stage,
    color: "#666666",
    bg: "rgba(85,85,85,0.06)",
    border: "rgba(85,85,85,0.2)",
  };
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
        style={{ background: cfg.color }}
      />
      {cfg.label}
    </span>
  );
}

/* ── Main component ──────────────────────────────────────── */
export function ActivitiesTable() {
  const [stage, setStage] = useState("");
  const [page, setPage]   = useState(1);

  const { data, isLoading, error } = useApiQuery(
    ["deals", stage, String(page)],
    () => crmApi.listDeals({ stage: stage || undefined, page, limit: 20 }),
  );

  const deals      = data?.items ?? [];
  const total      = data?.total ?? 0;
  const pageSize   = data?.limit ?? 20;
  const totalPages = Math.ceil(total / pageSize);

  const openDeals   = deals.filter((d) => d.stage !== "won" && d.stage !== "lost").length;
  const totalAmount = deals.reduce((s, d) => s + (d.amount ?? 0), 0);

  return (
    <div>
      {/* KPI summary */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        {[
          { label: "Total deals",     value: String(total),               icon: TrendingUp,  color: "var(--text-secondary)" },
          { label: "Deals actifs",    value: String(openDeals),           icon: Filter,      color: "#2979FF"               },
          { label: "Valeur pipeline", value: fmtAmount(totalAmount),      icon: DollarSign,  color: "#00E87A"               },
        ].map(({ label, value, icon: Icon, color }) => (
          <div
            key={label}
            className="rounded-xl px-4 py-3 flex items-center gap-3"
            style={{
              background: "rgba(255,255,255,0.025)",
              border: "1px solid var(--border-subtle)",
            }}
          >
            <div
              className="flex h-8 w-8 items-center justify-center rounded-lg flex-shrink-0"
              style={{
                background: "rgba(255,255,255,0.04)",
                border: "1px solid var(--border-subtle)",
              }}
            >
              <Icon size={13} style={{ color }} />
            </div>
            <div>
              <p
                className="font-mono-geist"
                style={{ color: "var(--text-muted)", fontSize: "10px", letterSpacing: "0.06em" }}
              >
                {label.toUpperCase()}
              </p>
              <p
                className="font-cinzel text-sm font-semibold mt-0.5"
                style={{ color: "var(--white-spectral)" }}
              >
                {value}
              </p>
            </div>
          </div>
        ))}
      </div>

      {/* Stage filter chips */}
      <div className="flex items-center gap-2 mb-6 flex-wrap">
        {FILTER_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            onClick={() => { setStage(opt.value); setPage(1); }}
            className="rounded-lg px-3 py-1.5 text-xs transition-all"
            style={{
              background:
                stage === opt.value ? "rgba(192,0,0,0.12)" : "rgba(255,255,255,0.03)",
              border: `1px solid ${
                stage === opt.value ? "var(--red-dark)" : "var(--border-subtle)"
              }`,
              color:
                stage === opt.value ? "var(--white-spectral)" : "var(--text-muted)",
              fontFamily: "var(--font-body)",
              cursor: "pointer",
            }}
          >
            {opt.label}
          </button>
        ))}
      </div>

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
            Impossible de charger les deals
          </p>
        </div>
      )}

      {!isLoading && !error && (
        <>
          <div
            className="rounded-xl overflow-hidden"
            style={{ border: "1px solid var(--border-subtle)" }}
          >
            <table className="w-full" style={{ borderCollapse: "collapse" }}>
              <thead>
                <tr
                  style={{
                    background: "rgba(255,255,255,0.02)",
                    borderBottom: "1px solid var(--border-subtle)",
                  }}
                >
                  {["Deal", "Étape", "Montant", "Probabilité", "Clôture", "Créé le"].map(
                    (h) => (
                      <th
                        key={h}
                        className="text-left px-4 py-3 font-mono-geist text-xs uppercase tracking-wider"
                        style={{ color: "var(--text-muted)", fontWeight: 500 }}
                      >
                        {h}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {deals.length === 0 && (
                  <tr>
                    <td colSpan={6} className="text-center py-12">
                      <p
                        className="font-cinzel text-xs tracking-widest"
                        style={{ color: "var(--text-muted)" }}
                      >
                        Aucun deal
                      </p>
                    </td>
                  </tr>
                )}
                {deals.map((deal: Deal, idx: number) => (
                  <tr
                    key={deal.id}
                    style={{
                      borderBottom:
                        idx < deals.length - 1
                          ? "1px solid var(--border-subtle)"
                          : "none",
                      transition: "background 0.12s",
                    }}
                    onMouseEnter={(e) =>
                      (e.currentTarget.style.background = "rgba(255,255,255,0.025)")
                    }
                    onMouseLeave={(e) =>
                      (e.currentTarget.style.background = "transparent")
                    }
                  >
                    <td className="px-4 py-3">
                      <span
                        className="font-cinzel text-xs font-semibold"
                        style={{ color: "var(--white-spectral)" }}
                      >
                        {deal.title}
                      </span>
                    </td>

                    <td className="px-4 py-3">
                      <StageBadge stage={deal.stage} />
                    </td>

                    <td className="px-4 py-3">
                      <span
                        className="font-mono-geist text-xs font-medium"
                        style={{
                          color: deal.amount ? "#00E87A" : "var(--text-muted)",
                        }}
                      >
                        {fmtAmount(deal.amount, deal.currency)}
                      </span>
                    </td>

                    <td className="px-4 py-3">
                      {deal.probability != null ? (
                        <div className="flex items-center gap-2">
                          <div
                            className="h-1 rounded-full overflow-hidden"
                            style={{ width: 48, background: "var(--border-subtle)" }}
                          >
                            <div
                              className="h-full rounded-full"
                              style={{
                                width: `${deal.probability}%`,
                                background:
                                  deal.probability >= 70
                                    ? "#00E87A"
                                    : deal.probability >= 40
                                    ? "#FBBD23"
                                    : "#C00000",
                              }}
                            />
                          </div>
                          <span
                            className="font-mono-geist text-xs"
                            style={{ color: "var(--text-secondary)" }}
                          >
                            {deal.probability}%
                          </span>
                        </div>
                      ) : (
                        <span style={{ color: "var(--text-muted)", fontSize: 11 }}>—</span>
                      )}
                    </td>

                    <td className="px-4 py-3">
                      <span
                        className="font-mono-geist text-xs"
                        style={{ color: "var(--text-secondary)" }}
                      >
                        {deal.close_date ? formatDate(deal.close_date) : "—"}
                      </span>
                    </td>

                    <td className="px-4 py-3">
                      <span
                        className="font-mono-geist text-xs"
                        style={{ color: "var(--text-muted)" }}
                      >
                        {formatDate(deal.created_at)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between mt-4">
              <span
                className="font-mono-geist text-xs"
                style={{ color: "var(--text-muted)" }}
              >
                Page {page} / {totalPages}
              </span>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="rounded px-3 py-1.5 text-xs"
                  style={{
                    background: "rgba(255,255,255,0.04)",
                    border: "1px solid var(--border-subtle)",
                    color: page === 1 ? "var(--text-muted)" : "var(--text-secondary)",
                    cursor: page === 1 ? "not-allowed" : "pointer",
                    fontFamily: "var(--font-body)",
                  }}
                >
                  ← Préc.
                </button>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages}
                  className="rounded px-3 py-1.5 text-xs"
                  style={{
                    background: "rgba(255,255,255,0.04)",
                    border: "1px solid var(--border-subtle)",
                    color:
                      page === totalPages ? "var(--text-muted)" : "var(--text-secondary)",
                    cursor: page === totalPages ? "not-allowed" : "pointer",
                    fontFamily: "var(--font-body)",
                  }}
                >
                  Suiv. →
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
