"use client";

import { useMemo } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { TrendingUp, TrendingDown } from "lucide-react";
import { Spinner } from "@/components/ui/spinner";
import { useApiQuery } from "@/hooks/useApi";
import { analyticsApi } from "@/lib/api";
import { C, CHART, tooltipStyle, fmtEur, fmtMonth } from "@/lib/chart-theme";

const FALLBACK_DATA = [
  { month: "Nov", mrr: 18200, new_mrr: 3100, churned_mrr: 400 },
  { month: "Déc", mrr: 20500, new_mrr: 3800, churned_mrr: 500 },
  { month: "Jan", mrr: 22100, new_mrr: 2900, churned_mrr: 1300 },
  { month: "Fév", mrr: 23400, new_mrr: 2600, churned_mrr: 1300 },
  { month: "Mar", mrr: 25700, new_mrr: 3800, churned_mrr: 1500 },
  { month: "Avr", mrr: 28400, new_mrr: 4100, churned_mrr: 1400 },
];

interface MrrPoint { month: string; mrr: number; new_mrr: number; churned_mrr: number }

function CustomTooltip({ active, payload, label }: {
  active?: boolean;
  payload?: Array<{ value: number }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  const mrr = payload[0]?.value ?? 0;
  return (
    <div style={tooltipStyle}>
      <p style={{ fontWeight: 600, marginBottom: 6, color: C.primary }}>{label}</p>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <Row color="#FF2020"  label="MRR total"  value={fmtEur(mrr)} />
      </div>
    </div>
  );
}

function Row({ color, label, value }: { color: string; label: string; value: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <span style={{ width: 8, height: 8, borderRadius: "50%", background: color, flexShrink: 0 }} />
      <span style={{ color: C.secondary }}>{label} :</span>
      <span style={{ color: C.primary, fontWeight: 500 }}>{value}</span>
    </div>
  );
}

export function MrrChart() {
  const { data: raw, isLoading } = useApiQuery(
    ["mrr-trend"],
    () => analyticsApi.getMrrTrend(6),
    { refetchInterval: 30_000, retry: false }
  );

  const { chartData, currentMrr, growth } = useMemo(() => {
    const points = raw?.result?.data_points;
    if (!points?.length) {
      return { chartData: FALLBACK_DATA, currentMrr: 28400, growth: 12.1 };
    }
    const chartData: MrrPoint[] = points.map((p) => ({
      month: fmtMonth(p.month),
      mrr: Math.round(parseFloat(p.mrr)),
      new_mrr: Math.round(parseFloat(p.new_mrr)),
      churned_mrr: Math.abs(Math.round(parseFloat(p.churned_mrr))),
    }));
    return {
      chartData,
      currentMrr: Math.round(parseFloat(raw?.result?.current_mrr ?? "0")),
      growth: raw?.result?.mom_growth_rate ?? 0,
    };
  }, [raw]);

  const isPositive = growth >= 0;
  const growthColor = isPositive ? C.green : C.red;

  return (
    <div className="tablette-marbre flex flex-col gap-4"
      style={{ background: "rgba(5,5,5,0.82)", border: "1px solid var(--red-dark)" }}
    >
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <p className="font-cinzel text-xs tracking-[0.2em] uppercase" style={{ color: "var(--red-doge)" }}>
            Revenu Récurrent Mensuel
          </p>
          <p className="text-xs mt-0.5" style={{ color: "var(--gray-silver)" }}>
            Abonnements actifs · 6 derniers mois
          </p>
          <p className="mt-2 text-3xl font-bold font-cinzel" style={{ color: "var(--white-spectral)", textShadow: "0 0 20px rgba(255,32,32,0.4)" }}>
            {fmtEur(currentMrr)}
          </p>
        </div>
        <div
          className="flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-sm font-semibold"
          style={{ background: `${growthColor}18`, color: growthColor, border: `1px solid ${growthColor}30` }}
        >
          {isPositive ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
          <span>{isPositive ? "+" : ""}{growth.toFixed(1)}% vs mois dernier</span>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={200}>
          <AreaChart data={chartData} margin={CHART.margin}>
            <defs>
              <linearGradient id="mrrGradBrand" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor="#FF2020" stopOpacity={0.4} />
                <stop offset="60%" stopColor="#8A0000" stopOpacity={0.12} />
                <stop offset="95%" stopColor="#050505" stopOpacity={0}   />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} vertical={false} />
            <XAxis
              dataKey="month"
              tick={{ fill: CHART.tick, fontSize: CHART.fontSize, fontFamily: CHART.font }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tickFormatter={(v: number) => fmtEur(v)}
              tick={{ fill: CHART.tick, fontSize: CHART.fontSize, fontFamily: CHART.font }}
              axisLine={false}
              tickLine={false}
              width={44}
            />
            <Tooltip content={<CustomTooltip />} cursor={{ stroke: "#8A0000", strokeWidth: 1, strokeDasharray: "4 4" }} />
            <Area
              type="monotone"
              dataKey="mrr"
              name="MRR total"
              stroke="#FF2020"
              strokeWidth={2.5}
              fill="url(#mrrGradBrand)"
              dot={false}
              activeDot={{ r: 5, fill: "#FF2020", stroke: "#050505", strokeWidth: 2 }}
            />
          </AreaChart>
        </ResponsiveContainer>

      {/* Legend */}
      <div className="flex items-center gap-4 text-xs" style={{ color: C.secondary }}>
        <span className="flex items-center gap-1.5">
          <span style={{ display:"inline-block", width:10, height:2, background: "#FF2020", borderRadius:1, boxShadow: "0 0 6px #FF202080" }} />
          MRR total
        </span>
        <span style={{ color: "var(--gray-silver)" }}>· mise à jour toutes les 30 s</span>
      </div>
    </div>
  );
}
