"use client";

import { TrendingUp, TrendingDown, Activity } from "lucide-react";

/* ── Static KPI data (placeholder until API is wired) ─── */
const KPI_DATA = [
  {
    label: "ARR Total",
    value: "$4.2M",
    change: "+18.4%",
    up: true,
    sub: "vs mois dernier",
    sparkPoints: "0,30 12,24 24,28 36,18 48,20 60,14 72,16 84,8 100,4",
    sparkColor: "#f5f5f5",
    glow: true,
  },
  {
    label: "Pipeline",
    value: "$1.8M",
    change: "+7.2%",
    up: true,
    sub: "cette semaine",
    sparkPoints: "0,28 16,20 32,22 48,16 64,10 80,14 100,6",
    sparkColor: "#00ff88",
    glow: false,
  },
  {
    label: "Deals actifs",
    value: "25",
    change: "−2",
    up: false,
    sub: "cette semaine",
    sparkPoints: "0,16 20,18 40,14 60,12 80,20 100,24",
    sparkColor: "#ff0000",
    glow: false,
  },
  {
    label: "Win Rate",
    value: "34%",
    change: "+3 pts",
    up: true,
    sub: "vs Q1",
    sparkPoints: "0,22 25,20 50,18 75,14 100,10",
    sparkColor: "#fbbf24",
    glow: false,
  },
];

/* ── Activity feed ───────────────────────────────────── */
const ACTIVITY = [
  { icon: "✦", text: <><strong style={{ color: "var(--text-primary)" }}>NovaTech Inc</strong> — deal passé en <span style={{ color: "var(--accent-red)" }}>Closing</span></>, time: "Il y a 14 min" },
  { icon: "◎", text: <>Contact <strong style={{ color: "var(--text-primary)" }}>Elena Park</strong> ajouté à Pulse AI</>, time: "Il y a 1h" },
  { icon: "▲", text: <><strong style={{ color: "var(--text-primary)" }}>Fintech Corp</strong> ARR mis à jour — $120K</>, time: "Il y a 3h" },
  { icon: "✦", text: <>Deal <strong style={{ color: "var(--text-primary)" }}>HealthStream</strong> marqué <strong style={{ color: "var(--accent-success)" }}>Won</strong></>, time: "Hier 16:42" },
];

/* ── Chart bars ──────────────────────────────────────── */
const BARS = [
  { label: "Nov", h: 55, accent: false },
  { label: "Déc", h: 42, accent: false },
  { label: "Jan", h: 68, accent: false },
  { label: "Fév", h: 72, accent: false },
  { label: "Mar", h: 85, accent: false },
  { label: "Avr", h: 91, accent: true },
];

export default function DashboardPage() {
  const today = new Date().toLocaleDateString("fr-FR", {
    weekday: "long", day: "numeric", month: "long", year: "numeric",
  });

  return (
    <div className="flex h-full flex-col">
      <main
        className="flex-1 overflow-y-auto px-6 py-6 space-y-8"
        style={{ background: "var(--bg-base)" }}
      >
        {/* Sub-header */}
        <div className="flex items-center">
          <p className="text-xs capitalize" style={{ color: "var(--text-muted)" }}>{today}</p>
        </div>

        {/* ── KPI section ── */}
        <section>
          <div
            className="mb-4 flex items-center gap-3 text-xs font-bold uppercase tracking-widest"
            style={{ color: "var(--text-muted)" }}
          >
            Key Metrics
            <span className="flex-1 h-px" style={{ background: "var(--border-subtle)" }} />
          </div>

          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            {KPI_DATA.map((kpi) => (
              <div
                key={kpi.label}
                className="relative overflow-hidden rounded-xl p-5 flex flex-col gap-2"
                style={{
                  background: "var(--bg-surface)",
                  border: "1px solid var(--border-default)",
                  boxShadow: kpi.glow ? "var(--shadow-glow)" : "var(--shadow-card)",
                }}
              >
                <p className="text-xs font-medium uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
                  {kpi.label}
                </p>
                <div className="flex items-end justify-between gap-2">
                  <p
                    className="font-orbitron text-2xl font-bold tracking-tight leading-none"
                    style={{ color: "var(--text-primary)" }}
                  >
                    {kpi.value}
                  </p>
                  <div
                    className="flex items-center gap-1 text-xs font-semibold"
                    style={{ color: kpi.up ? "var(--accent-success)" : "var(--accent-red)" }}
                  >
                    {kpi.up ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                    {kpi.change}
                  </div>
                </div>
                <p className="text-xs" style={{ color: "var(--text-muted)" }}>{kpi.sub}</p>
                {/* Sparkline */}
                <svg viewBox="0 0 100 36" preserveAspectRatio="none" className="h-7 w-full mt-1">
                  <polyline
                    points={kpi.sparkPoints}
                    fill="none"
                    stroke={kpi.sparkColor}
                    strokeWidth="1.5"
                    opacity="0.5"
                  />
                </svg>
              </div>
            ))}
          </div>
        </section>

        {/* ── Chart + Activity ── */}
        <section className="grid gap-4 lg:grid-cols-[2fr_1fr]">
          {/* Bar chart */}
          <div
            className="rounded-xl p-6"
            style={{ background: "var(--bg-surface)", border: "1px solid var(--border-default)", boxShadow: "var(--shadow-card)" }}
          >
            <div className="flex items-start justify-between mb-6">
              <div>
                <p className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>Revenue mensuel</p>
                <p
                  className="font-orbitron text-2xl font-bold mt-1"
                  style={{ color: "var(--text-primary)" }}
                >
                  $348K{" "}
                  <span className="font-sans text-sm font-normal" style={{ color: "var(--text-muted)" }}>/ Avril</span>
                </p>
              </div>
              <div className="flex gap-2">
                <span
                  className="rounded px-2.5 py-1 text-xs font-medium"
                  style={{ background: "var(--bg-elevated)", color: "var(--text-primary)", border: "1px solid var(--border-strong)" }}
                >
                  Monthly
                </span>
                <span
                  className="rounded px-2.5 py-1 text-xs font-medium"
                  style={{ color: "var(--text-muted)" }}
                >
                  Quarterly
                </span>
              </div>
            </div>

            {/* Bars */}
            <div className="flex items-end gap-1.5 h-40 pb-6">
              {BARS.map((bar) => (
                <div key={bar.label} className="relative flex-1 flex flex-col items-center gap-1.5">
                  <div
                    className="w-full rounded-t transition-all duration-200"
                    style={{
                      height: `${bar.h}%`,
                      background: bar.accent ? "var(--accent-red)" : "var(--bg-elevated)",
                      border: bar.accent ? "none" : "1px solid var(--border-strong)",
                      boxShadow: bar.accent ? "0 0 18px rgba(255,0,0,0.45)" : "none",
                    }}
                  />
                  <span className="text-xs absolute -bottom-5" style={{ color: "var(--text-muted)" }}>
                    {bar.label}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Activity feed */}
          <div
            className="rounded-xl overflow-hidden"
            style={{ background: "var(--bg-surface)", border: "1px solid var(--border-default)", boxShadow: "var(--shadow-card)" }}
          >
            <div
              className="px-5 pt-5 pb-0 flex items-center gap-3 text-xs font-bold uppercase tracking-widest"
              style={{ color: "var(--text-muted)" }}
            >
              <Activity size={11} />
              Activité récente
            </div>
            <div className="mt-3">
              {ACTIVITY.map((item, i) => (
                <div
                  key={i}
                  className="flex gap-3 px-5 py-4"
                  style={{ borderTop: i > 0 ? "1px solid var(--border-subtle)" : "none" }}
                >
                  <div
                    className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg text-xs mt-0.5"
                    style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-default)", color: "var(--text-muted)" }}
                  >
                    {item.icon}
                  </div>
                  <div>
                    <p className="text-xs leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                      {item.text}
                    </p>
                    <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>{item.time}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
