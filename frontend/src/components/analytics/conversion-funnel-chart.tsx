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
  LabelList,
} from "recharts";
import { Spinner } from "@/components/ui/spinner";
import { useApiQuery } from "@/hooks/useApi";
import { analyticsApi } from "@/lib/api";
import { C, CHART, tooltipStyle, healthColor } from "@/lib/chart-theme";

const STAGE_LABELS: Record<string, string> = {
  prospecting:  "Prospection",
  qualification:"Qualification",
  proposal:     "Proposition",
  negotiation:  "Négociation",
  closing:      "Closing",
  won:          "Gagné",
};

const FALLBACK_STAGES = [
  { stage: "Prospection",   entered: 120, conversion_rate: 68, isBottleneck: false },
  { stage: "Qualification", entered: 82,  conversion_rate: 54, isBottleneck: true  },
  { stage: "Proposition",   entered: 44,  conversion_rate: 61, isBottleneck: false },
  { stage: "Négociation",   entered: 27,  conversion_rate: 74, isBottleneck: false },
  { stage: "Closing",       entered: 20,  conversion_rate: 80, isBottleneck: false },
];

interface FunnelStage { stage: string; entered: number; conversion_rate: number; isBottleneck: boolean }

function CustomTooltip({ active, payload }: {
  active?: boolean;
  payload?: Array<{ payload: FunnelStage }>;
}) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div style={tooltipStyle}>
      <p style={{ fontWeight: 600, marginBottom: 6, color: C.primary }}>{d.stage}</p>
      <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
        <p style={{ color: C.secondary }}>
          Contacts entrés : <span style={{ color: C.primary, fontWeight: 500 }}>{d.entered}</span>
        </p>
        <p style={{ color: C.secondary }}>
          Taux de conversion : <span style={{ color: healthColor(d.conversion_rate, 60, 40), fontWeight: 600 }}>{d.conversion_rate}%</span>
        </p>
        {d.isBottleneck && (
          <p style={{ color: C.magenta, marginTop: 4 }}>⚠ Goulot d'étranglement</p>
        )}
      </div>
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
    const bottleneckKey = raw.result.bottleneck_stage ?? null;
    const chartData: FunnelStage[] = stages.map((s) => ({
      stage:           STAGE_LABELS[s.stage] ?? s.stage,
      entered:         s.entered,
      conversion_rate: Math.round(s.conversion_rate * 100),
      isBottleneck:    s.stage === bottleneckKey,
    }));
    const bottleneck = bottleneckKey
      ? (STAGE_LABELS[bottleneckKey] ?? bottleneckKey)
      : null;
    return {
      chartData,
      overallConversion: Math.round(raw.result.overall_conversion * 100),
      bottleneck,
    };
  }, [raw]);

  return (
    <div className="tablette-marbre flex flex-col gap-4"
      style={{ background: "rgba(5,5,5,0.82)", border: "1px solid var(--red-dark)" }}
    >
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <p className="font-cinzel text-xs tracking-[0.2em] uppercase" style={{ color: "var(--red-doge)" }}>
            Pipeline de vente
          </p>
          <p className="text-xs mt-0.5" style={{ color: "var(--gray-silver)" }}>
            Taux de conversion par étape
          </p>
          <div className="flex items-baseline gap-2 mt-2">
            <p className="text-3xl font-bold font-cinzel" style={{ color: "var(--white-spectral)", textShadow: "0 0 20px rgba(255,32,32,0.4)" }}>{overallConversion}%</p>
            <p className="text-xs" style={{ color: "var(--gray-silver)" }}>lead → client</p>
          </div>
        </div>
        {bottleneck && (
          <div
            className="rounded-md px-2.5 py-1.5"
            style={{ background: `${C.magenta}12`, border: `1px solid ${C.magenta}30` }}
          >
            <p className="text-xs font-medium" style={{ color: C.magenta }}>⚠ Goulot : {bottleneck}</p>
          </div>
        )}
      </div>

      {isLoading ? (
        <div className="flex h-48 items-center justify-center">
          <Spinner size="lg" />
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={210}>
          <BarChart
            layout="vertical"
            data={chartData}
            margin={{ top: 4, right: 48, left: 0, bottom: 0 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} horizontal={false} />
            <XAxis
              type="number"
              domain={[0, 100]}
              tickFormatter={(v: number) => `${v}%`}
              tick={{ fill: CHART.tick, fontSize: CHART.fontSize, fontFamily: CHART.font }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              type="category"
              dataKey="stage"
              width={88}
              tick={{ fill: CHART.tick, fontSize: CHART.fontSize, fontFamily: CHART.font }}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip content={<CustomTooltip />} cursor={{ fill: "rgba(192,0,0,0.08)" }} />
            <Bar dataKey="conversion_rate" name="Conversion" radius={[0, 4, 4, 0]} maxBarSize={20}>
              {chartData.map((d, i) => (
                <Cell
                  key={i}
                  fill={d.isBottleneck ? C.magenta : healthColor(d.conversion_rate, 60, 40)}
                  fillOpacity={0.85}
                />
              ))}
              <LabelList
                dataKey="conversion_rate"
                position="right"
                formatter={(v: number) => `${v}%`}
                style={{ fill: C.secondary, fontSize: 11, fontFamily: CHART.font }}
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}

      {/* Legend */}
      <div className="flex items-center gap-4 text-xs flex-wrap" style={{ color: "var(--gray-silver)" }}>
        <span className="flex items-center gap-1">
          <span style={{ width:8, height:8, borderRadius:2, background: "#D4A000", display:"inline-block" }} />
          Bon (&gt;60%)
        </span>
        <span className="flex items-center gap-1">
          <span style={{ width:8, height:8, borderRadius:2, background: "#C00000", display:"inline-block" }} />
          Moyen (40–60%)
        </span>
        <span className="flex items-center gap-1">
          <span style={{ width:8, height:8, borderRadius:2, background: "#FF1A1A", display:"inline-block" }} />
          À améliorer (&lt;40%)
        </span>
      </div>
    </div>
  );
}
