import { SequencesList } from "@/components/sequences/sequences-list";

export default function SequencesPage() {
  return (
    <div className="flex h-full flex-col">
      <main className="flex-1 overflow-y-auto px-6 py-6">
        <SequencesList />
      </main>
    </div>
  );
}
