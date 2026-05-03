"use client";

import { Search, Building2 } from "lucide-react";
import { useState } from "react";
import { Spinner } from "@/components/ui/spinner";
import { useApiQuery } from "@/hooks/useApi";
import { crmApi } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import type { Account } from "@/types";

/* ── Industry badge palette ──────────────────────────────── */
const INDUSTRY_COLORS: Record<string, { color: string; bg: string; border: string }> = {
  SaaS:       { color: "#2979FF", bg: "rgba(41,121,255,0.08)",  border: "rgba(41,121,255,0.25)" },
  Tech:       { color: "#2979FF", bg: "rgba(41,121,255,0.08)",  border: "rgba(41,121,255,0.25)" },
  Finance:    { color: "#FBBD23", bg: "rgba(251,189,35,0.08)",  border: "rgba(251,189,35,0.25)" },
  Healthcare: { color: "#00E87A", bg: "rgba(0,232,122,0.08)",   border: "rgba(0,232,122,0.25)" },
  Retail:     { color: "#C07000", bg: "rgba(192,112,0,0.10)",   border: "rgba(192,112,0,0.30)" },
  Media:      { color: "#9B59B6", bg: "rgba(155,89,182,0.10)",  border: "rgba(155,89,182,0.30)" },
};

function IndustryBadge({ industry }: { industry?: string }) {
  const cfg = (industry && INDUSTRY_COLORS[industry]) ?? {
    color: "#666",
    bg: "rgba(85,85,85,0.06)",
    border: "rgba(85,85,85,0.2)",
  };
  return (
    <span
      className="inline-flex items-center rounded px-2 py-0.5 text-xs"
      style={{
        background: cfg.bg,
        color: cfg.color,
        border: `1px solid ${cfg.border}`,
        fontFamily: "var(--font-body)",
      }}
    >
      {industry ?? "—"}
    </span>
  );
}

function fmtArr(arr?: number): string {
  if (!arr) return "—";
  if (arr >= 1_000_000) return `${(arr / 1_000_000).toFixed(1)}M€`;
  if (arr >= 1_000)     return `${(arr / 1_000).toFixed(0)}K€`;
  return `${arr}€`;
}

/* ── Main component ──────────────────────────────────────── */
export function CompaniesTable() {
  const [query, setQuery]   = useState("");
  const [page, setPage]     = useState(1);

  const { data, isLoading, error } = useApiQuery(
    ["accounts", query, String(page)],
    () => crmApi.listAccounts({ query: query || undefined, page, limit: 20 }),
  );

  const accounts    = data?.items ?? [];
  const total       = data?.total ?? 0;
  const pageSize    = data?.limit ?? 20;
  const totalPages  = Math.ceil(total / pageSize);

  return (
    <div>
      {/* Search row */}
      <div className="flex items-center gap-3 mb-6">
        <div className="relative flex-1 max-w-sm">
          <Search
            size={13}
            className="absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none"
            style={{ color: "var(--text-muted)" }}
          />
          <input
            type="text"
            placeholder="Rechercher une société…"
            value={query}
            onChange={(e) => { setQuery(e.target.value); setPage(1); }}
            className="w-full rounded-lg pl-8 pr-3 py-2 text-sm outline-none"
            style={{
              background: "rgba(255,255,255,0.03)",
              border: "1px solid var(--border-subtle)",
              color: "var(--text-primary)",
              fontFamily: "var(--font-body)",
            }}
          />
        </div>
        <span className="font-mono-geist text-xs" style={{ color: "var(--text-muted)" }}>
          {total} société{total !== 1 ? "s" : ""}
        </span>
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
            Impossible de charger les sociétés
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
                  {["Société", "Domaine", "Secteur", "Taille", "ARR", "Créée le"].map((h) => (
                    <th
                      key={h}
                      className="text-left px-4 py-3 font-mono-geist text-xs uppercase tracking-wider"
                      style={{ color: "var(--text-muted)", fontWeight: 500 }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {accounts.length === 0 && (
                  <tr>
                    <td colSpan={6} className="text-center py-12">
                      <p
                        className="font-cinzel text-xs tracking-widest"
                        style={{ color: "var(--text-muted)" }}
                      >
                        Aucune société
                      </p>
                    </td>
                  </tr>
                )}
                {accounts.map((acc: Account, idx: number) => (
                  <tr
                    key={acc.id}
                    style={{
                      borderBottom:
                        idx < accounts.length - 1
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
                      <div className="flex items-center gap-2.5">
                        <div
                          className="flex h-7 w-7 items-center justify-center rounded-lg flex-shrink-0"
                          style={{
                            background:
                              "radial-gradient(circle at 38% 32%, #1A0A00 0%, #050505 80%)",
                            border: "1px solid var(--border-default)",
                          }}
                        >
                          <Building2 size={12} style={{ color: "var(--text-muted)" }} />
                        </div>
                        <span
                          className="font-cinzel text-xs font-semibold"
                          style={{ color: "var(--white-spectral)" }}
                        >
                          {acc.name}
                        </span>
                      </div>
                    </td>

                    <td className="px-4 py-3">
                      {acc.domain ? (
                        <span
                          className="font-mono-geist text-xs"
                          style={{ color: "var(--text-secondary)" }}
                        >
                          {acc.domain}
                        </span>
                      ) : (
                        <span style={{ color: "var(--text-muted)", fontSize: 11 }}>—</span>
                      )}
                    </td>

                    <td className="px-4 py-3">
                      <IndustryBadge industry={acc.industry} />
                    </td>

                    <td className="px-4 py-3">
                      <span
                        className="font-mono-geist text-xs"
                        style={{ color: "var(--text-secondary)" }}
                      >
                        {acc.size ?? "—"}
                      </span>
                    </td>

                    <td className="px-4 py-3">
                      <span
                        className="font-mono-geist text-xs font-medium"
                        style={{ color: acc.arr ? "#00E87A" : "var(--text-muted)" }}
                      >
                        {fmtArr(acc.arr)}
                      </span>
                    </td>

                    <td className="px-4 py-3">
                      <span
                        className="font-mono-geist text-xs"
                        style={{ color: "var(--text-muted)" }}
                      >
                        {formatDate(acc.created_at)}
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
