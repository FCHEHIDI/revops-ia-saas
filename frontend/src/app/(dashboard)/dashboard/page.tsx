"use client";

import Image from "next/image";
import { Activity, BarChart2, Zap } from "lucide-react";
import {
  TabletteHeader,
  TabletteDivider,
  TabletteBadge,
} from "@/components/ui/tablette-marbre";

// ─── KPI data ──────────────────────────────────────────────────────────────
const KPI_DATA = [
  {
    label: "ARR Total",
    value: "$4.2M",
    delta: "↑ +18.4% vs mois dernier",
    trend: "positive",
    icon: "⚜",
    sparkPoints: "0,30 12,24 24,28 36,18 48,20 60,14 72,16 84,8 100,4",
    sparkColor: "#C00000",
    active: true,
  },
  {
    label: "Pipeline",
    value: "$1.8M",
    delta: "↑ +7.2% cette semaine",
    trend: "positive",
    icon: "◈",
    sparkPoints: "0,28 16,20 32,22 48,16 64,10 80,14 100,6",
    sparkColor: "#8A0000",
    active: false,
  },
  {
    label: "Deals actifs",
    value: "25",
    delta: "↓ −2 cette semaine",
    trend: "negative",
    icon: "◉",
    sparkPoints: "0,16 20,18 40,14 60,12 80,20 100,24",
    sparkColor: "#FF1A1A",
    active: false,
  },
  {
    label: "Win Rate",
    value: "34%",
    delta: "↑ +3 pts vs Q1",
    trend: "positive",
    icon: "✦",
    sparkPoints: "0,22 25,20 50,18 75,14 100,10",
    sparkColor: "#8A0000",
    active: false,
  },
];

// ─── Activity feed ──────────────────────────────────────────────────────────
const ACTIVITY = [
  {
    glyph: "✦",
    text: "NovaTech Inc",
    detail: "Deal passé en Closing",
    time: "Il y a 14 min",
    badge: "Closing",
    badgeStatus: "default" as const,
  },
  {
    glyph: "◎",
    text: "Elena Park",
    detail: "Contact ajouté à Pulse AI",
    time: "Il y a 1h",
    badge: "Nouveau",
    badgeStatus: "success" as const,
  },
  {
    glyph: "▲",
    text: "Fintech Corp",
    detail: "ARR mis à jour — $120K",
    time: "Il y a 3h",
    badge: "Mis à jour",
    badgeStatus: "warning" as const,
  },
  {
    glyph: "✦",
    text: "HealthStream",
    detail: "Deal marqué Won",
    time: "Hier 16:42",
    badge: "Won",
    badgeStatus: "success" as const,
  },
];

// ─── Chart bars ─────────────────────────────────────────────────────────────
const BARS = [
  { label: "Nov", h: 55, accent: false },
  { label: "Déc", h: 42, accent: false },
  { label: "Jan", h: 68, accent: false },
  { label: "Fév", h: 72, accent: false },
  { label: "Mar", h: 85, accent: false },
  { label: "Avr", h: 100, accent: true },
];

// ═══════════════════════════════════════════════════════════════════════════
// Page
// ═══════════════════════════════════════════════════════════════════════════

export default function DashboardPage() {
  const today = new Date().toLocaleDateString("fr-FR", {
    weekday: "long", day: "numeric", month: "long", year: "numeric",
  });

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <main className="flex-1 overflow-y-auto chat-scroll">

        {/* ── Hero visuel — Salle du Conseil ─────────────────────────── */}
        <div className="relative w-full overflow-hidden" style={{ height: 220 }}>
          <div
            className="absolute inset-0"
            style={{
              backgroundImage: "url('/visuels/dashboard.png')",
              backgroundSize: "cover",
              backgroundPosition: "center 75%",
              filter: "brightness(0.55) saturate(0.8)",
            }}
          />
          <div
            className="absolute inset-0"
            style={{
              background: "linear-gradient(to bottom, rgba(5,5,5,0.1) 0%, rgba(5,5,5,0.5) 60%, rgba(5,5,5,1) 100%)",
            }}
          />
          <div
            className="absolute inset-0 pointer-events-none"
            style={{
              background: "linear-gradient(90deg, rgba(138,0,0,0.15) 0%, transparent 15%, transparent 85%, rgba(138,0,0,0.15) 100%)",
            }}
          />
          {/* ── Icône décorative filigrane ── */}
          <Image
            src="/icons/dashboard-icon.png"
            alt=""
            aria-hidden="true"
            width={780}
            height={780}
            style={{
              position: "absolute",
              right: "4%",
              top: "50%",
              transform: "translateY(-50%)",
              width: 780,
              height: 780,
              objectFit: "contain",
              opacity: 0.35,
              filter: "blur(0.3px)",
              pointerEvents: "none",
            }}
          />
          <div className="absolute bottom-0 left-0 right-0 px-8 pb-6">
            <p className="font-cinzel text-xs tracking-[0.3em] uppercase mb-1" style={{ color: "var(--red-doge)" }}>
              Salle du Conseil
            </p>
            <h1
              className="font-cinzel text-3xl font-bold"
              style={{ color: "var(--white-spectral)", textShadow: "0 0 32px rgba(192,0,0,0.4)" }}
            >
              Dashboard
            </h1>
            <p className="text-xs mt-1 capitalize" style={{ color: "var(--gray-silver)", fontFamily: "var(--font-body)" }}>
              {today}
            </p>
          </div>
        </div>

        {/* ── Contenu principal ──────────────────────────────────────── */}
        <div className="px-8 py-8 space-y-10">

          {/* KPIs ──────────────────────────────────────────────────── */}
          <section>
            <div className="flex items-center gap-4 mb-5">
              <span className="font-cinzel text-xs tracking-[0.25em] uppercase" style={{ color: "var(--red-doge)" }}>
                ⚜ Indicateurs Clés
              </span>
              <div className="flex-1 h-px" style={{ background: "linear-gradient(90deg, var(--red-dark), transparent)" }} />
            </div>
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
              {KPI_DATA.map((kpi) => (
                <div key={kpi.label} className={`tablette-marbre tablette-metrique${kpi.active ? " active" : ""}`}>
                  <div className="flex items-center justify-between mb-3">
                    <span className="font-cinzel text-xs tracking-[0.12em] uppercase" style={{ color: "var(--gray-silver)" }}>
                      {kpi.label}
                    </span>
                    <span
                      style={{
                        width: 28, height: 28, borderRadius: "50%",
                        background: "radial-gradient(circle, #8A0000, #220000)",
                        border: "1px solid var(--red-dark)",
                        display: "flex", alignItems: "center", justifyContent: "center",
                        fontSize: "0.7rem", boxShadow: "var(--glow-red)", flexShrink: 0,
                      }}
                    >
                      {kpi.icon}
                    </span>
                  </div>
                  <div className="tm-value">{kpi.value}</div>
                  <div className={`tm-delta ${kpi.trend}`} style={{ fontSize: "0.7rem", marginTop: 6 }}>
                    {kpi.delta}
                  </div>
                  <svg viewBox="0 0 100 36" preserveAspectRatio="none" className="w-full mt-3" style={{ height: 28 }}>
                    <polyline
                      points={kpi.sparkPoints}
                      fill="none"
                      stroke={kpi.sparkColor}
                      strokeWidth="1.5"
                      opacity="0.7"
                    />
                  </svg>
                </div>
              ))}
            </div>
          </section>

          {/* Chart + Activité ──────────────────────────────────────── */}
          <section className="grid gap-5 lg:grid-cols-[2fr_1fr]">

            {/* Tablette Graphique */}
            <div className="tablette-marbre tablette-graphique">
              <TabletteHeader
                icon={<BarChart2 size={14} color="var(--red-doge)" />}
                title="Revenue mensuel"
                subtitle="Salle du Conseil — Vue mensuelle"
              />
              <div className="flex items-end justify-between mb-5">
                <div>
                  <span
                    className="text-2xl font-bold"
                    style={{ color: "var(--white-spectral)", textShadow: "var(--glow-red)", fontFamily: "var(--font-mono)" }}
                  >
                    $348K
                  </span>
                  <span className="ml-2 text-xs" style={{ color: "var(--gray-silver)", fontFamily: "var(--font-body)" }}>
                    / Avril
                  </span>
                </div>
                <div className="flex gap-2">
                  <TabletteBadge>Monthly</TabletteBadge>
                  <span className="text-xs px-2" style={{ color: "var(--gray-silver)", fontFamily: "var(--font-body)" }}>
                    Quarterly
                  </span>
                </div>
              </div>
              <TabletteDivider />
              <div className="flex items-end gap-2 pt-4" style={{ height: 130 }}>
                {BARS.map((bar) => (
                  <div key={bar.label} className="relative flex-1 flex flex-col items-center gap-1">
                    <div
                      className="w-full rounded-t transition-all duration-300"
                      style={{
                        height: `${bar.h}%`,
                        background: bar.accent
                          ? "linear-gradient(to top, #8A0000, #C00000)"
                          : "radial-gradient(circle at 50% 0%, #1A1A1A, #0A0A0A)",
                        border: bar.accent ? "1px solid var(--red-doge)" : "1px solid rgba(138,0,0,0.2)",
                        boxShadow: bar.accent ? "var(--glow-red-strong)" : "none",
                      }}
                    />
                    <span
                      className="absolute -bottom-5"
                      style={{
                        color: bar.accent ? "var(--red-doge)" : "var(--gray-silver)",
                        fontFamily: "var(--font-body)", fontSize: "0.6rem", letterSpacing: "0.08em",
                      }}
                    >
                      {bar.label}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Tablette Activité */}
            <div className="tablette-marbre">
              <TabletteHeader
                icon={<Activity size={14} color="var(--red-doge)" />}
                title="Activité récente"
                subtitle="Registre des événements"
              />
              <TabletteDivider />
              <div className="space-y-0">
                {ACTIVITY.map((item, i) => (
                  <div
                    key={i}
                    className="flex gap-3 py-3"
                    style={{ borderTop: i > 0 ? "1px solid rgba(138,0,0,0.12)" : "none" }}
                  >
                    <div
                      style={{
                        width: 28, height: 28, borderRadius: "50%", flexShrink: 0,
                        background: "radial-gradient(circle, #220000, #050505)",
                        border: "1px solid var(--red-dark)",
                        display: "flex", alignItems: "center", justifyContent: "center",
                        fontSize: "0.65rem", color: "var(--red-doge)",
                      }}
                    >
                      {item.glyph}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-0.5">
                        <span className="font-cinzel text-xs font-semibold truncate" style={{ color: "var(--white-spectral)" }}>
                          {item.text}
                        </span>
                        <TabletteBadge status={item.badgeStatus}>{item.badge}</TabletteBadge>
                      </div>
                      <p className="text-xs" style={{ color: "var(--gray-silver)", fontFamily: "var(--font-body)" }}>
                        {item.detail}
                      </p>
                      <p className="text-xs mt-0.5" style={{ color: "var(--red-dark)", fontFamily: "var(--font-mono)", fontSize: "0.6rem", letterSpacing: "0.05em" }}>
                        {item.time}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
              <TabletteDivider />
              <button
                className="w-full font-cinzel text-xs tracking-[0.15em] uppercase py-2 transition-all duration-200"
                style={{ color: "var(--red-doge)", background: "transparent", border: "none", cursor: "pointer" }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLButtonElement).style.color = "var(--red-glow)";
                  (e.currentTarget as HTMLButtonElement).style.textShadow = "var(--glow-red)";
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLButtonElement).style.color = "var(--red-doge)";
                  (e.currentTarget as HTMLButtonElement).style.textShadow = "none";
                }}
              >
                Voir tout le registre →
              </button>
            </div>
          </section>

          {/* Deals en vedette ──────────────────────────────────────── */}
          <section>
            <div className="flex items-center gap-4 mb-5">
              <span className="font-cinzel text-xs tracking-[0.25em] uppercase" style={{ color: "var(--red-doge)" }}>
                ◈ Deals en Vedette
              </span>
              <div className="flex-1 h-px" style={{ background: "linear-gradient(90deg, var(--red-dark), transparent)" }} />
            </div>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              {[
                { name: "NovaTech Inc", arr: "$240K", stage: "Closing", status: "default" as const, icon: "🏛" },
                { name: "HealthStream", arr: "$120K", stage: "Won", status: "success" as const, icon: "⚕" },
                { name: "Fintech Corp", arr: "$98K", stage: "Négociation", status: "warning" as const, icon: "◈" },
              ].map((deal) => (
                <div key={deal.name} className="tablette-marbre tablette-interactive" style={{ cursor: "pointer" }}>
                  <div className="flex items-start justify-between gap-2">
                    <TabletteHeader
                      icon={<span style={{ fontSize: "1rem" }}>{deal.icon}</span>}
                      title={deal.name}
                      subtitle={deal.arr + " ARR"}
                    />
                    <TabletteBadge status={deal.status}>{deal.stage}</TabletteBadge>
                  </div>
                  <div className="tm-divider" style={{ marginTop: 12, marginBottom: 10 }} />
                  <div className="flex items-center gap-2">
                    <Zap size={11} color="var(--red-dark)" />
                    <span className="text-xs" style={{ color: "var(--gray-silver)", fontFamily: "var(--font-body)" }}>
                      Prochaine action requise
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </section>

        </div>
      </main>
    </div>
  );
}
