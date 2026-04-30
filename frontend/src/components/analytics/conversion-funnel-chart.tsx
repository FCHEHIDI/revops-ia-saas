"use client";

import { useMemo } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { Card } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { useApiQuery } from "@/hooks/useApi";
import { analyticsApi } from "@/lib/api";

const STAGE_LABELS: Record<string, string> = {
  prospecting: "Prospection",
  qualification: "Qualification",
  proposal: "Proposition",
  negotiation: "Négociation",
  closing: "Closing",
  won: "Gagné",
};

const FALLBACK_STAGES = [
  { stage: "Prospection",   entered: 120, conversion_rate: 68 },
  { stage: "Qualification", entered: 82,  conversion_rate: 54 },
  { stage: "Proposition",   entered: 44,  conversion_rate: 61 },
  { stage: "Négociation",   entered: 27,  conversion_rate: 74 },
  { stage: "Closing",       entered: 20,  conversion_rate: 80 },
];

// Color interpolation: deep indigo → emerald
const COLORS = ["#6366f1", "#818cf8", "#a78bfa", "#34d399", "#10b981"];

interface TooltipPayload {
  payload?: {
    stage: string;
    entered: number;
    conversion_rate: number;
  };
}

function CustomTooltip({ active, payload }: { active?: boolean; payload?: TooltipPayload[] }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  if (!d) return null;
  return (
    <div className="rounded-lg border border-white/10 bg-bg-card px-3 py-2 shadow-lg text-xs">
      <p className="font-medium text-text-primary mb-1">{d.stage}</p>
      <p className="text-text-muted">Entrées: <span className="text-text-primary font-medium">{d.entered}</span></p>
      <p className="text-text-muted">Taux: <span className="text-emerald-400 font-medium">{d.conversion_rate.toFixed(0)}%</span></p>
    </div>
  );
}

export function ConversionFunnelChart() {
  const { data: raw, isLoading } = useApiQuery(
    ["funnel-analysis"],
    () => analyticsApi.getFunnelAnalysis(),
    { refetchInterval: 30_000, retry: false }
  );

  const { chartData, overallConversion, bottleneck } = useMemo(() => {
    const stages = raw?.result?.stages;
    if (!stages?.length) {
      return { chartData: FALLBACK_STAGES, overallConversion: 16.7, bottleneck: "Qualification" };
    }
    const chartData = stages.map((s) => ({
      stage: STAGE_LABELS[s.stage] ?? s.stage,
      entered: s.entered,
      conversion_rate: Math.round(s.conversion_rate * 100),
    }));
    const bottleneck = raw.result.bottleneck_stage
      ? (STAGE_LABELS[raw.result.bottleneck_stage] ?? raw.result.bottleneck_stage)
      : null;
    return {
      chartData,
      overallConversion: Math.round(raw.result.overall_conversion * 100),
      bottleneck,
    };
  }, [raw]);

  return (
    <Card className="flex flex-col gap-4">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-medium text-text-muted uppercase tracking-wide">Funnel de conversion</p>
          <p className="mt-1 text-2xl font-bold text-text-primary">{overallConversion}%</p>
          <p className="text-xs text-text-muted">Taux global lead → client</p>
        </div>
        {bottleneck && (
          <div className="rounded-md bg-amber-500/10 border border-amber-500/20 px-2 py-1">
            <p className="text-xs text-amber-400">⚠ Goulot : {bottleneck}</p>
          </div>
        )}
      </div>

      {isLoading ? (
        <div className="flex h-48 items-center justify-center">
          <Spinner size="lg" />
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={chartData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
            <XAxis dataKey="stage" tick={{ fill: "#9ca3af", fontSize: 10 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: "#9ca3af", fontSize: 11 }} axisLine={false} tickLine={false} />
            <Tooltip content={<CustomTooltip />} />
            <Bar dataKey="entered" name="Contacts" radius={[4, 4, 0, 0]}>
              {chartData.map((_, i) => (
                <Cell key={i} fill={COLORS[i % COLORS.length]} fillOpacity={0.85} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
    </Card>
  );
}
