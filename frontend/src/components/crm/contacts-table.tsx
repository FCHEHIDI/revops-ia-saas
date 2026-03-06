"use client";

import { Badge } from "@/components/ui/badge";
import { Spinner } from "@/components/ui/spinner";
import { useApiQuery } from "@/hooks/useApi";
import { crmApi } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import type { Contact, ContactStatus } from "@/types";

const statusVariant: Record<ContactStatus, "success" | "info" | "warning" | "error" | "neutral"> = {
  active: "success",
  customer: "info",
  lead: "warning",
  inactive: "neutral",
  churned: "error",
};

const statusLabel: Record<ContactStatus, string> = {
  active: "Actif",
  customer: "Client",
  lead: "Lead",
  inactive: "Inactif",
  churned: "Churné",
};

export function ContactsTable() {
  const { data, isLoading, error } = useApiQuery(
    ["contacts"],
    () => crmApi.listContacts()
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
      <div className="rounded-lg border border-red-800/50 bg-red-900/10 p-6 text-center text-sm text-red-400">
        Erreur lors du chargement des contacts : {error.message}
      </div>
    );
  }

  const contacts: Contact[] = data?.items ?? [];

  if (contacts.length === 0) {
    return (
      <div className="rounded-xl border border-slate-700 bg-slate-800 p-12 text-center">
        <p className="text-slate-400">Aucun contact trouvé.</p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-slate-700">
      <table className="w-full text-sm">
        <thead className="bg-slate-800/80 border-b border-slate-700">
          <tr>
            {["Nom", "Email", "Entreprise", "Statut", "Créé le"].map((h) => (
              <th key={h} className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wide">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-700/50 bg-slate-800">
          {contacts.map((contact) => (
            <tr key={contact.id} className="hover:bg-slate-700/30 transition-colors">
              <td className="px-4 py-3 font-medium text-slate-100">
                {contact.first_name} {contact.last_name}
              </td>
              <td className="px-4 py-3 text-slate-400">{contact.email}</td>
              <td className="px-4 py-3 text-slate-400">{contact.company ?? "—"}</td>
              <td className="px-4 py-3">
                <Badge variant={statusVariant[contact.status]}>
                  {statusLabel[contact.status]}
                </Badge>
              </td>
              <td className="px-4 py-3 text-slate-500">{formatDate(contact.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
