import { MetricsCards } from "@/components/analytics/metrics-cards";
import { MrrChart } from "@/components/analytics/mrr-chart";
import { ConversionFunnelChart } from "@/components/analytics/conversion-funnel-chart";
import { BillingStatusChart } from "@/components/analytics/billing-status-chart";
import { ChurnRateChart } from "@/components/analytics/churn-rate-chart";

export default function AnalyticsPage() {
  return (
    <div className="flex h-full flex-col">
      <main className="flex-1 overflow-y-auto chat-scroll">

        {/* ── Hero — Salle des Archives ─────────────────────── */}
        <div
          style={{
            height: 220,
            position: "relative",
            overflow: "hidden",
            flexShrink: 0,
          }}
        >
          {/* Image fond */}
          <div
            style={{
              position: "absolute", inset: 0,
              backgroundImage: "url('/visuels/analytics.png')",
              backgroundSize: "cover",
              backgroundPosition: "center 72%",
              filter: "brightness(0.5) saturate(0.7)",
            }}
          />
          {/* Gradient bas */}
          <div
            style={{
              position: "absolute", inset: 0,
              background: "linear-gradient(to bottom, rgba(5,5,5,0) 30%, rgba(5,5,5,0.85) 80%, #050505 100%)",
            }}
          />
          {/* Vignettes latérales */}
          <div style={{ position: "absolute", inset: 0, background: "linear-gradient(to right, rgba(138,0,0,0.18) 0%, transparent 25%, transparent 75%, rgba(138,0,0,0.18) 100%)" }} />
          {/* Brume rouge au sol */}
          <div style={{ position: "absolute", bottom: 0, left: 0, right: 0, height: 60, background: "linear-gradient(to top, rgba(138,0,0,0.12), transparent)" }} />

          {/* Texte */}
          <div
            style={{
              position: "absolute", bottom: 28, left: 0, right: 0,
              display: "flex", flexDirection: "column", alignItems: "center", gap: 6,
            }}
          >
            <span
              className="font-cinzel tracking-[0.35em] uppercase text-xs"
              style={{ color: "var(--red-doge)", textShadow: "0 0 20px rgba(192,0,0,0.8)" }}
            >
              Salle des Archives
            </span>
            <h1
              className="font-cinzel font-bold text-3xl tracking-[0.08em]"
              style={{
                color: "var(--white-spectral)",
                textShadow: "0 0 24px rgba(255,26,26,0.5), 0 2px 8px rgba(0,0,0,0.9)",
              }}
            >
              Analytics
            </h1>
            <p
              className="text-xs tracking-[0.15em]"
              style={{ color: "var(--gray-silver)", fontFamily: "var(--font-body)" }}
            >
              Métriques de revenus, pipeline &amp; rétention
            </p>
          </div>
        </div>

        {/* ── Contenu ───────────────────────────────────────── */}
        <div className="px-8 py-8 space-y-6">

          {/* KPIs */}
          <section>
            <p
              className="font-cinzel text-xs tracking-[0.25em] uppercase mb-4"
              style={{ color: "var(--red-doge)" }}
            >
              ⚜ Métriques Clés
            </p>
            <MetricsCards />
          </section>

          {/* Revenus & Pipeline */}
          <section>
            <p
              className="font-cinzel text-xs tracking-[0.25em] uppercase mb-4"
              style={{ color: "var(--red-doge)" }}
            >
              ◈ Revenus &amp; Pipeline
            </p>
            <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
              <MrrChart />
              <ConversionFunnelChart />
            </div>
          </section>

          {/* Facturation & Rétention */}
          <section>
            <p
              className="font-cinzel text-xs tracking-[0.25em] uppercase mb-4"
              style={{ color: "var(--red-doge)" }}
            >
              ◉ Facturation &amp; Rétention
            </p>
            <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
              <BillingStatusChart />
              <ChurnRateChart />
            </div>
          </section>

        </div>
      </main>
    </div>
  );
}
