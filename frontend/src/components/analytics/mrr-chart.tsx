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
  Legend,
} from "recharts";
import { format, parseISO } from "date-fns";
import { fr } from "date-fns/locale";
import { TrendingUp, TrendingDown } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { useApiQuery } from "@/hooks/useApi";
import { analyticsApi } from "@/lib/api";

const FALLBACK_DATA = [
  { month: "Nov 2025", mrr: 18200, new_mrr: 3100, churned_mrr: -400 },
  { month: "Déc 2025", mrr: 20500, new_mrr: 3800, churned_mrr: -500 },
  { month: "Jan 2026", mrr: 22100, new_mrr: 2900, churned_mrr: -1300 },
  { month: "Fév 2026", mrr: 23400, new_mrr: 2600, churned_mrr: -1300 },
  { month: "Mar 2026", mrr: 25700, new_mrr: 3800, churned_mrr: -1500 },
  { month: "Avr 2026", mrr: 28400, new_mrr: 4100, churned_mrr: -1400 },
];

function formatEur(value: number) {
  if (value >= 1000) return `${(value / 1000).toFixed(0)}k€`;
  return `${value}€`;
}

interface TooltipPayloadItem {
  name: string;
  value: number;
  color: string;
}

function CustomTooltip({ active, payload, label }: {
  active?: boolean;
  payload?: TooltipPayloadItem[];
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-white/10 bg-bg-card px-3 py-2 shadow-lg text-xs">
      <p className="font-medium text-text-primary mb-1">{label}</p>
      {payload.map((p) => (
        <div key={p.name} className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full" style={{ background: p.color }} />
          <span className="text-text-muted">{p.name}:</span>
          <span className="font-medium text-text-primary">{formatEur(Math.abs(p.value))}</span>
        </div>
      ))}
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
    const chartData = points.map((p) => ({
      month: format(parseISO(p.month), "MMM yyyy", { locale: fr }),
      mrr: Math.round(parseFloat(p.mrr)),
      new_mrr: Math.round(parseFloat(p.new_mrr)),
      churned_mrr: -Math.abs(Math.round(parseFloat(p.churned_mrr))),
    }));
    return {
      chartData,
      currentMrr: Math.round(parseFloat(raw.result.current_mrr)),
      growth: raw.result.mom_growth_rate,
    };
  }, [raw]);

  const isPositive = growth >= 0;

  return (
    <Card className="flex flex-col gap-4">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-medium text-text-muted uppercase tracking-wide">MRR Trend</p>
          <p className="mt-1 text-2xl font-bold text-text-primary">{formatEur(currentMrr)}</p>
        </div>
        <div className={`flex items-center gap-1 text-sm font-medium ${isPositive ? "text-emerald-400" : "text-red-400"}`}>
          {isPositive ? <TrendingUp size={16} /> : <TrendingDown size={16} />}
          <span>{isPositive ? "+" : ""}{growth.toFixed(1)}% MoM</span>
        </div>
      </div>

      {isLoading ? (
        <div className="flex h-48 items-center justify-center">
          <Spinner size="lg" />
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={200}>
          <AreaChart data={chartData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="mrrGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="newGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
            <XAxis dataKey="month" tick={{ fill: "#9ca3af", fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis tickFormatter={formatEur} tick={{ fill: "#9ca3af", fontSize: 11 }} axisLine={false} tickLine={false} width={48} />
            <Tooltip content={<CustomTooltip />} />
            <Legend wrapperStyle={{ fontSize: 12, color: "#9ca3af" }} />
            <Area type="monotone" dataKey="mrr" name="MRR total" stroke="#6366f1" strokeWidth={2} fill="url(#mrrGrad)" />
            <Area type="monotone" dataKey="new_mrr" name="Nouveau MRR" stroke="#10b981" strokeWidth={2} fill="url(#newGrad)" />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </Card>
  );
}
