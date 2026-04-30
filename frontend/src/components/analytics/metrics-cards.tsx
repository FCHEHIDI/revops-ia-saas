"use client";

import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { useApiQuery } from "@/hooks/useApi";
import { analyticsApi } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { Metric } from "@/types";

function MetricCard({ metric }: { metric: Metric }) {
  const isIncrease = metric.changeType === "increase";
  const isDecrease = metric.changeType === "decrease";
  const hasChange = metric.change !== undefined && metric.changeType !== undefined;

  return (
    <Card className="flex flex-col gap-3">
      <p className="text-xs font-medium text-text-muted uppercase tracking-wide">{metric.label}</p>
      <div className="flex items-end justify-between gap-2">
        <div>
          <span className="text-2xl font-bold text-text-primary">{metric.value}</span>
          {metric.unit && (
            <span className="ml-1 text-sm text-text-muted">{metric.unit}</span>
          )}
        </div>
        {hasChange && (
          <div
            className={cn(
              "flex items-center gap-1 text-xs font-medium",
              isIncrease && "text-emerald-400",
              isDecrease && "text-red",
              !isIncrease && !isDecrease && "text-text-muted"
            )}
          >
            {isIncrease && <TrendingUp size={14} />}
            {isDecrease && <TrendingDown size={14} />}
            {!isIncrease && !isDecrease && <Minus size={14} />}
            <span>{metric.change! > 0 ? "+" : ""}{metric.change}%</span>
          </div>
        )}
      </div>
      {metric.period && (
        <p className="text-xs text-text-muted">{metric.period}</p>
      )}
    </Card>
  );
}

// Demo metrics shown when the API isn't available yet
const placeholderMetrics: Metric[] = [
  { label: "Contacts actifs",      value: "312",   changeType: "increase", change: 8.4,  period: "vs mois dernier" },
  { label: "MRR",                  value: "28 400", unit: "€", changeType: "increase", change: 12.1, period: "Avril 2026" },
  { label: "Taux de conversion",   value: "34",    unit: "%", changeType: "increase", change: 3.0,  period: "vs Q1" },
  { label: "Séquences actives",    value: "7",     changeType: "neutral",  period: "sur 12 créées" },
];

export function MetricsCards() {
  const { data, isLoading, error } = useApiQuery(
    ["metrics"],
    () => analyticsApi.getMetrics()
  );

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Spinner size="lg" />
      </div>
    );
  }

  const metrics = error ? placeholderMetrics : (data ?? placeholderMetrics);

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {metrics.map((metric, i) => (
        <MetricCard key={i} metric={metric} />
      ))}
    </div>
  );
}
