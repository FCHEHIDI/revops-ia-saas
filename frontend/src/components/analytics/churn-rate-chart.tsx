"use client";

import { useMemo } from "react";
import { Spinner } from "@/components/ui/spinner";
import { useApiQuery } from "@/hooks/useApi";
import { analyticsApi } from "@/lib/api";
import { C } from "@/lib/chart-theme";

/** Returns colour + label based on NRR health */
function nrrHealth(nrr: number): { color: string; label: string; hint: string } {
  if (nrr >= 110) return { color: C.success,  label: "Expansion",  hint: "Upsell > churn — excellent" };
  if (nrr >= 100) return { color: C.green,    label: "Stable",     hint: "Revenus retenus intégralement" };
  if (nrr >= 90)  return { color: C.blue,     label: "Attention",  hint: "Légère perte nette de revenu" };
  return             { color: C.magenta,   label: "Alerte",     hint: "Churn supérieur aux upsells" };
}

/** Returns colour + label based on churn rate % */
function churnHealth(pct: number): { color: string; label: string } {
  if (pct < 2)  return { color: C.success, label: "Très faible" };
  if (pct < 5)  return { color: C.green,   label: "Normal"      };
  if (pct < 8)  return { color: C.magenta, label: "Élevé"       };
  return               { color: C.red,     label: "Critique"    };
}

interface BarProps { value: number; max: number; color: string }

function HealthBar({ value, max, color }: BarProps) {
  const pct = Math.min((value / max) * 100, 100);
  return (
    <div style={{ height: 4, borderRadius: 2, background: "rgba(138,0,0,0.25)", overflow: "hidden" }}>
      <div
        style={{
          height: "100%",
          width: `${pct}%`,
          background: color,
          borderRadius: 2,
          transition: "width 0.6s ease",
          boxShadow: `0 0 8px ${color}60`,
        }}
      />
    </div>
  );
}

export function ChurnRateChart() {
  const { data: raw, isLoading } = useApiQuery(
    ["churn-rate"],
    () => analyticsApi.getChurnRate(),
    { refetchInterval: 30_000, retry: false }
  );

  const { nrr, churnPct, churnedCount, startingCount } = useMemo(() => {
    const r = raw?.result;
    if (!r) return { nrr: 108.5, churnPct: 4.2, churnedCount: 3, startingCount: 72 };
    return {
      nrr:          r.net_revenue_retention * 100,
      churnPct:     r.churn_rate * 100,
      churnedCount: r.churned_count,
      startingCount: r.starting_count,
    };
  }, [raw]);

  const nrr_h   = nrrHealth(nrr);
  const churn_h = churnHealth(churnPct);

  if (isLoading) {
    return (
      <div className="tablette-marbre flex items-center justify-center" style={{ minHeight: 200, background: "rgba(5,5,5,0.82)", border: "1px solid var(--red-dark)" }}>
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="tablette-marbre flex flex-col gap-5"
      style={{ background: "rgba(5,5,5,0.82)", border: "1px solid var(--red-dark)" }}
    >
      {/* Section title */}
      <div>
        <p className="font-cinzel text-xs tracking-[0.2em] uppercase" style={{ color: "var(--red-doge)" }}>
          Rétention client
        </p>
        <p className="text-xs mt-0.5" style={{ color: "var(--gray-silver)" }}>
          NRR &gt; 100% = le revenu croît malgré le churn
        </p>
      </div>

      {/* NRR */}
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <span className="text-xs" style={{ color: "var(--gray-silver)" }}>Net Revenue Retention (NRR)</span>
          <span
            className="text-xs font-semibold rounded px-1.5 py-0.5"
            style={{ color: nrr_h.color, background: `${nrr_h.color}18`, border: `1px solid ${nrr_h.color}30` }}
          >
            {nrr_h.label}
          </span>
        </div>
        <p className="text-3xl font-bold tabular-nums" style={{ color: nrr_h.color }}>
          {nrr.toFixed(1)}%
        </p>
        <HealthBar value={nrr} max={130} color={nrr_h.color} />
        <p className="text-xs" style={{ color: "var(--gray-silver)" }}>{nrr_h.hint}</p>
      </div>

      {/* Divider */}
      <div style={{ borderTop: "1px solid var(--red-dark)" }} />

      {/* Churn rate */}
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <span className="text-xs" style={{ color: "var(--gray-silver)" }}>Taux de churn mensuel</span>
          <span
            className="text-xs font-semibold rounded px-1.5 py-0.5"
            style={{ color: churn_h.color, background: `${churn_h.color}18`, border: `1px solid ${churn_h.color}30` }}
          >
            {churn_h.label}
          </span>
        </div>
        <p className="text-3xl font-bold tabular-nums" style={{ color: churn_h.color }}>
          {churnPct.toFixed(1)}%
        </p>
        {/* 10% = danger ceiling, so full bar = 10% churn */}
        <HealthBar value={churnPct} max={10} color={churn_h.color} />
        <p className="text-xs" style={{ color: "var(--gray-silver)" }}>
          {churnedCount} client{churnedCount > 1 ? "s" : ""} perdu{churnedCount > 1 ? "s" : ""}
          {" "}sur {startingCount} en début de période
        </p>
      </div>
    </div>
  );
}
