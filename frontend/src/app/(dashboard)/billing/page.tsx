import { Header } from "@/components/layout/header";
import { InvoicesList } from "@/components/billing/invoices-list";

export default function BillingPage() {
  return (
    <div className="flex h-full flex-col">
      <Header title="Facturation" />
      <main className="flex-1 overflow-y-auto px-6 py-6">
        <InvoicesList />
      </main>
    </div>
  );
}
