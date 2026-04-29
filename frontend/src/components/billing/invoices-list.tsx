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

  if (error) {
    return (
      <div className="rounded-lg border border-red/30 bg-red-dim/30 p-6 text-center text-sm text-red">
        Erreur lors du chargement des factures : {error.message}
      </div>
    );
  }

  const invoices: Invoice[] = data?.items ?? [];

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
