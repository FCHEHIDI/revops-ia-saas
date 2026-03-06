import { Header } from "@/components/layout/header";
import { MetricsCards } from "@/components/analytics/metrics-cards";

export default function AnalyticsPage() {
  return (
    <div className="flex h-full flex-col">
      <Header title="Analytics" />
      <main className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
        <div>
          <h2 className="text-sm font-medium text-slate-500 uppercase tracking-wide mb-4">
            Métriques clés
          </h2>
          <MetricsCards />
        </div>
      </main>
    </div>
  );
}
