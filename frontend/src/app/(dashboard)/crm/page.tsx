import { ContactsTable } from "@/components/crm/contacts-table";

export default function CrmPage() {
  return (
    <div className="flex h-full flex-col">
      <main className="flex-1 overflow-y-auto px-6 py-6">
        <ContactsTable />
      </main>
    </div>
  );
}
