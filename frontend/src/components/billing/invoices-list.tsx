"use client";

import { Spinner } from "@/components/ui/spinner";
import { useApiQuery } from "@/hooks/useApi";
import { billingApi } from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/utils";
import type { Invoice, InvoiceStatus } from "@/types";

/* ── Palette statut vénitienne ── */
const STATUS_CFG: Record<InvoiceStatus, { label: string; color: string; bg: string; border: string; glyph: string }> = {
  paid:      { label: "Payée",      color: "#D4A000", bg: "rgba(212,160,0,0.12)",  border: "rgba(212,160,0,0.35)", glyph: "✦" },
  pending:   { label: "En attente", color: "#C07000", bg: "rgba(192,112,0,0.12)", border: "rgba(192,112,0,0.35)", glyph: "◌" },
  draft:     { label: "Brouillon",  color: "#7A5555", bg: "rgba(122,85,85,0.10)",  border: "rgba(122,85,85,0.30)", glyph: "◎" },
  overdue:   { label: "En retard",  color: "#FF1A1A", bg: "rgba(255,26,26,0.12)", border: "rgba(255,26,26,0.40)", glyph: "⚠" },
  cancelled: { label: "Annulée",    color: "#5A3535", bg: "rgba(90,53,53,0.08)",   border: "rgba(90,53,53,0.25)", glyph: "✕" },
};

const DEMO_INVOICES: Invoice[] = [
  { id: "INV-2026-042", tenant_id: "", number: "INV-2026-042", amount: 4800,  currency: "EUR", status: "paid",      due_date: "2026-04-01", issued_at: "2026-03-15", customer_name: "NovaTech Inc",   customer_email: "billing@novatech.io" },
  { id: "INV-2026-041", tenant_id: "", number: "INV-2026-041", amount: 2200,  currency: "EUR", status: "paid",      due_date: "2026-03-15", issued_at: "2026-02-28", customer_name: "Pulse AI",       customer_email: "billing@pulseai.io" },
  { id: "INV-2026-043", tenant_id: "", number: "INV-2026-043", amount: 6500,  currency: "EUR", status: "pending",   due_date: "2026-05-01", issued_at: "2026-04-14", customer_name: "Fintech Corp",   customer_email: "billing@fintechcorp.io" },
  { id: "INV-2026-044", tenant_id: "", number: "INV-2026-044", amount: 1800,  currency: "EUR", status: "overdue",   due_date: "2026-04-10", issued_at: "2026-03-25", customer_name: "HealthStream",   customer_email: "billing@healthstream.com" },
  { id: "INV-2026-040", tenant_id: "", number: "INV-2026-040", amount: 3200,  currency: "EUR", status: "paid",      due_date: "2026-03-01", issued_at: "2026-02-14", customer_name: "DataSync Dev",   customer_email: "billing@datasync.dev" },
  { id: "INV-2026-039", tenant_id: "", number: "INV-2026-039", amount: 9900,  currency: "EUR", status: "draft",     due_date: "2026-05-15", issued_at: "2026-04-25", customer_name: "RetoolPro",      customer_email: "billing@retoolpro.com" },
];

function StatusBadge({ status }: { status: InvoiceStatus }) {
  const cfg = STATUS_CFG[status];
  return (
    <span
      className="inline-flex items-center gap-1 rounded px-2 py-0.5 font-cinzel text-xs tracking-[0.1em] uppercase"
      style={{ color: cfg.color, background: cfg.bg, border: `1px solid ${cfg.border}` }}
    >
      <span style={{ fontSize: "0.6rem" }}>{cfg.glyph}</span>
      {cfg.label}
    </span>
  );
}

export function InvoicesList() {
  const { data, isLoading, error } = useApiQuery(
    ["invoices"],
    () => billingApi.listInvoices()
  );

  const invoices: Invoice[] = (isLoading || error || !data) ? DEMO_INVOICES : (data?.items ?? DEMO_INVOICES);

  if (invoices.length === 0) {
    return (
      <div className="tablette-marbre p-12 text-center">
        <p className="font-cinzel text-sm tracking-[0.2em]" style={{ color: "var(--gray-silver)" }}>
          Aucune facture dans les registres.
        </p>
      </div>
    );
  }

  /* ── totaux rapides ── */
  const totalOverdue = invoices.filter(i => i.status === "overdue").reduce((s, i) => s + (i.amount ?? 0), 0);
  const totalPending = invoices.filter(i => i.status === "pending").reduce((s, i) => s + (i.amount ?? 0), 0);
  const totalPaid    = invoices.filter(i => i.status === "paid").reduce((s, i) => s + (i.amount ?? 0), 0);

  return (
    <div className="flex flex-col gap-6">

      {/* ── Résumé KPI ── */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: "Encaissé",   value: formatCurrency(totalPaid, "EUR"),    color: "#D4A000", glow: "rgba(212,160,0,0.25)" },
          { label: "En attente", value: formatCurrency(totalPending, "EUR"), color: "#C07000", glow: "rgba(192,112,0,0.20)" },
          { label: "En retard",  value: formatCurrency(totalOverdue, "EUR"), color: "#FF1A1A", glow: "rgba(255,26,26,0.25)" },
        ].map(({ label, value, color, glow }) => (
          <div
            key={label}
            className="tablette-marbre tablette-metrique flex flex-col gap-1"
            style={{ borderColor: color + "44" }}
          >
            <span className="font-cinzel text-xs tracking-[0.2em] uppercase" style={{ color: "var(--gray-silver)" }}>
              {label}
            </span>
            <span
              className="font-cinzel text-xl font-bold"
              style={{ color, textShadow: `0 0 14px ${glow}` }}
            >
              {value}
            </span>
          </div>
        ))}
      </div>

      {/* ── Séparateur vénitien ── */}
      <div className="flex items-center gap-3">
        <div style={{ flex: 1, height: 1, background: "linear-gradient(to right, transparent, var(--red-dark))" }} />
        <span className="font-cinzel text-xs tracking-[0.35em] uppercase" style={{ color: "var(--red-doge)" }}>
          ◈ Registre des Factures
        </span>
        <div style={{ flex: 1, height: 1, background: "linear-gradient(to left, transparent, var(--red-dark))" }} />
      </div>

      {/* ── Table ── */}
      <div
        className="tablette-marbre overflow-hidden"
        style={{ padding: 0, border: "1px solid var(--red-dark)" }}
      >
        <table className="w-full text-sm">
          <thead>
            <tr style={{ borderBottom: "1px solid var(--red-dark)", background: "rgba(34,0,0,0.6)" }}>
              {["N° Facture", "Client", "Montant", "Statut", "Échéance", "Émise le"].map((h) => (
                <th
                  key={h}
                  className="px-4 py-3 text-left font-cinzel text-xs tracking-[0.15em] uppercase"
                  style={{ color: "var(--red-doge)" }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {invoices.map((invoice, idx) => (
              <tr
                key={invoice.id}
                style={{
                  borderBottom: idx < invoices.length - 1 ? "1px solid rgba(138,0,0,0.18)" : "none",
                  transition: "background 0.15s ease",
                  cursor: "default",
                }}
                className="group"
                onMouseEnter={e => (e.currentTarget.style.background = "rgba(138,0,0,0.10)")}
                onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
              >
                <td className="px-4 py-3" style={{ fontFamily: "var(--font-mono)", fontSize: "0.78rem", color: "var(--red-doge)", letterSpacing: "0.05em" }}>
                  {invoice.number}
                </td>
                <td className="px-4 py-3">
                  <div className="font-medium" style={{ color: "var(--white-spectral)" }}>{invoice.customer_name}</div>
                  <div className="text-xs" style={{ color: "var(--gray-silver)", fontFamily: "var(--font-mono)", fontSize: "0.68rem" }}>
                    {invoice.customer_email}
                  </div>
                </td>
                <td className="px-4 py-3 font-bold font-cinzel" style={{ color: "var(--white-spectral)", letterSpacing: "0.05em" }}>
                  {formatCurrency(invoice.amount, invoice.currency)}
                </td>
                <td className="px-4 py-3">
                  <StatusBadge status={invoice.status} />
                </td>
                <td className="px-4 py-3" style={{ color: invoice.status === "overdue" ? "#FF1A1A" : "var(--gray-silver)", fontFamily: "var(--font-mono)", fontSize: "0.8rem" }}>
                  {formatDate(invoice.due_date)}
                </td>
                <td className="px-4 py-3" style={{ color: "var(--gray-silver)", fontFamily: "var(--font-mono)", fontSize: "0.8rem" }}>
                  {formatDate(invoice.issued_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
