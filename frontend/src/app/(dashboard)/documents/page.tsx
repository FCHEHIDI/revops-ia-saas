import { DocumentsUpload } from "@/components/documents/documents-upload";

export default function DocumentsPage() {
  return (
    <div className="flex h-full flex-col">
      <main className="flex-1 overflow-y-auto px-6 py-6">
        <DocumentsUpload />
      </main>
    </div>
  );
}
