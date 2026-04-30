"use client";

import { useMemo } from "react";
import {
  RadialBarChart,
  RadialBar,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import { Card } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { useApiQuery } from "@/hooks/useApi";
import { analyticsApi } from "@/lib/api";

interface TooltipPayload {
  name: string;
  value: number;
}

function CustomTooltip({ active, payload }: { active?: boolean; payload?: TooltipPayload[] }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-white/10 bg-bg-card px-3 py-2 shadow-lg text-xs">
      <p className="text-text-muted">{payload[0].name}: <span className="text-text-primary font-medium">{payload[0].value.toFixed(1)}%</span></p>
    </div>
  );
}

export function ChurnRateChart() {
  const { data: raw, isLoading } = useApiQuery(
    ["churn-rate"],
    () => analyticsApi.getChurnRate(),
    { refetchInterval: 30_000, retry: false }
  );

  const { churnRate, nrr, churnedCount } = useMemo(() => {
    const r = raw?.result;
    if (!r) return { churnRate: 4.2, nrr: 108.5, churnedCount: 3 };
    return {
      churnRate: r.churn_rate * 100,
      nrr: r.net_revenue_retention * 100,
      churnedCount: r.churned_count,
    };
  }, [raw]);

  const gaugeData = [
    { name: "NRR",   value: Math.min(nrr, 130),   fill: "#10b981" },
    { name: "Churn", value: Math.min(churnRate * 3, 100), fill: "#ef4444" },
  ];

  return (
    <Card className="flex flex-col gap-4">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-medium text-text-muted uppercase tracking-wide">Rétention client</p>
          <p className="mt-1 text-2xl font-bold text-emerald-400">{nrr.toFixed(1)}%</p>
          <p className="text-xs text-text-muted">NRR · {churnedCount} churné{churnedCount > 1 ? "s" : ""}</p>
        </div>
        <div className="text-right">
          <p className="text-xs text-text-muted">Churn rate</p>
          <p className={`text-lg font-bold ${churnRate > 5 ? "text-red-400" : "text-amber-400"}`}>
            {churnRate.toFixed(1)}%
          </p>
        </div>
      </div>

      {isLoading ? (
        <div className="flex h-48 items-center justify-center">
          <Spinner size="lg" />
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={180}>
          <RadialBarChart
            cx="50%"
            cy="80%"
            innerRadius="50%"
            outerRadius="90%"
            startAngle={180}
            endAngle={0}
            data={gaugeData}
          >
            <RadialBar dataKey="value" cornerRadius={6} background={{ fill: "rgba(255,255,255,0.03)" }} />
            <Tooltip content={<CustomTooltip />} />
          </RadialBarChart>
        </ResponsiveContainer>
      )}
    </Card>
  );
}
