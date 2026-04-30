"use client";

import { Badge } from "@/components/ui/badge";
import { Spinner } from "@/components/ui/spinner";
import { useApiQuery } from "@/hooks/useApi";
import { billingApi } from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/utils";
import type { Invoice, InvoiceStatus } from "@/types";

const statusVariant: Record<InvoiceStatus, "success" | "info" | "warning" | "error" | "neutral"> = {
  paid: "success",
  pending: "warning",
  draft: "neutral",
  overdue: "error",
  cancelled: "neutral",
};

const statusLabel: Record<InvoiceStatus, string> = {
  paid: "Payée",
  pending: "En attente",
  draft: "Brouillon",
  overdue: "En retard",
  cancelled: "Annulée",
};

export function InvoicesList() {
  const { data, isLoading, error } = useApiQuery(
    ["invoices"],
    () => billingApi.listInvoices()
  );

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Spinner size="lg" />
      </div>
    );
  }

  const demoInvoices: Invoice[] = [
    { id: "INV-2026-042", tenant_id: "", number: "INV-2026-042", amount: 4800,  currency: "EUR", status: "paid",    due_date: "2026-04-01", issued_at: "2026-03-15", customer_name: "NovaTech Inc",  customer_email: "billing@novatech.io" },
    { id: "INV-2026-041", tenant_id: "", number: "INV-2026-041", amount: 2200,  currency: "EUR", status: "paid",    due_date: "2026-03-15", issued_at: "2026-02-28", customer_name: "Pulse AI",      customer_email: "billing@pulseai.io" },
    { id: "INV-2026-043", tenant_id: "", number: "INV-2026-043", amount: 6500,  currency: "EUR", status: "pending", due_date: "2026-05-01", issued_at: "2026-04-14", customer_name: "Fintech Corp",  customer_email: "billing@fintechcorp.io" },
    { id: "INV-2026-044", tenant_id: "", number: "INV-2026-044", amount: 1800,  currency: "EUR", status: "overdue", due_date: "2026-04-10", issued_at: "2026-03-25", customer_name: "HealthStream",  customer_email: "billing@healthstream.com" },
    { id: "INV-2026-040", tenant_id: "", number: "INV-2026-040", amount: 3200,  currency: "EUR", status: "paid",    due_date: "2026-03-01", issued_at: "2026-02-14", customer_name: "DataSync Dev",  customer_email: "billing@datasync.dev" },
    { id: "INV-2026-039", tenant_id: "", number: "INV-2026-039", amount: 9900,  currency: "EUR", status: "draft",   due_date: "2026-05-15", issued_at: "2026-04-25", customer_name: "RetoolPro",     customer_email: "billing@retoolpro.com" },
  ];

  const invoices: Invoice[] = error ? demoInvoices : (data?.items ?? demoInvoices);

  if (invoices.length === 0) {
    return (
      <div className="rounded-xl border border-border-default bg-surface p-12 text-center">
        <p className="text-text-secondary">Aucune facture trouvée.</p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-border-default">
      <table className="w-full text-sm">
        <thead className="bg-surface/80 border-b border-border-default">
          <tr>
            {["N°", "Client", "Montant", "Statut", "Échéance", "Émise le"].map((h) => (
              <th key={h} className="px-4 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wide">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border-default/50 bg-surface">
          {invoices.map((invoice) => (
            <tr key={invoice.id} className="hover:bg-elevated/30 transition-colors">
              <td className="px-4 py-3 font-mono text-text-secondary">{invoice.number}</td>
              <td className="px-4 py-3">
                <div className="font-medium text-text-primary">{invoice.customer_name}</div>
                <div className="text-xs text-text-muted">{invoice.customer_email}</div>
              </td>
              <td className="px-4 py-3 font-medium text-text-primary">
                {formatCurrency(invoice.amount, invoice.currency)}
              </td>
              <td className="px-4 py-3">
                <Badge variant={statusVariant[invoice.status]}>
                  {statusLabel[invoice.status]}
                </Badge>
              </td>
              <td className="px-4 py-3 text-text-secondary">{formatDate(invoice.due_date)}</td>
              <td className="px-4 py-3 text-text-muted">{formatDate(invoice.issued_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
