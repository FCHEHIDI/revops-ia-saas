import { MetricsCards } from "@/components/analytics/metrics-cards";
import { MrrChart } from "@/components/analytics/mrr-chart";
import { ConversionFunnelChart } from "@/components/analytics/conversion-funnel-chart";
import { BillingStatusChart } from "@/components/analytics/billing-status-chart";
import { ChurnRateChart } from "@/components/analytics/churn-rate-chart";

export default function AnalyticsPage() {
  return (
    <div className="flex h-full flex-col">
      <main className="flex-1 overflow-y-auto px-6 py-6 space-y-8">

        {/* KPI cards */}
        <section>
          <h2 className="text-xs font-medium text-text-muted uppercase tracking-wide mb-4">
            Métriques clés
          </h2>
          <MetricsCards />
        </section>

        {/* Charts row 1 — MRR (large) + Funnel */}
        <section>
          <h2 className="text-xs font-medium text-text-muted uppercase tracking-wide mb-4">
            Revenus &amp; Pipeline
          </h2>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <MrrChart />
            <ConversionFunnelChart />
          </div>
        </section>

        {/* Charts row 2 — Billing + Churn */}
        <section>
          <h2 className="text-xs font-medium text-text-muted uppercase tracking-wide mb-4">
            Facturation &amp; Rétention
          </h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <BillingStatusChart />
            <ChurnRateChart />
          </div>
        </section>

      </main>
    </div>
  );
}
