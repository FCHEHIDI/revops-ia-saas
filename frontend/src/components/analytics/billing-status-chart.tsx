"use client";

import { useMemo } from "react";
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { Spinner } from "@/components/ui/spinner";
import { useApiQuery } from "@/hooks/useApi";
import { billingApi } from "@/lib/api";
import { C, tooltipStyle } from "@/lib/chart-theme";

/** Map invoice status → brand colour + French label */
const STATUS: Record<string, { label: string; color: string }> = {
  paid:      { label: "Payée",     color: "#D4A000" }, // or vénitien
  pending:   { label: "En attente",color: "#C07000" }, // ambre vénitien
  overdue:   { label: "En retard", color: "#FF1A1A" }, // rouge incandescent
  draft:     { label: "Brouillon", color: "#5A3535" }, // muted vénitien
  cancelled: { label: "Annulée",   color: "#2A1A1A" }, // très sombre
};

interface SliceData { name: string; value: number; color: string; amount: number }

function CustomTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload: SliceData }> }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div style={tooltipStyle}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
        <span style={{ width: 8, height: 8, borderRadius: "50%", background: d.color, flexShrink: 0 }} />
        <span style={{ fontWeight: 600, color: C.primary }}>{d.name}</span>
      </div>
      <p style={{ color: C.secondary }}>
        Factures : <span style={{ color: C.primary, fontWeight: 500 }}>{d.value}</span>
      </p>
      {d.amount > 0 && (
        <p style={{ color: C.secondary }}>
          Montant : <span style={{ color: C.primary, fontWeight: 500 }}>
            {d.amount.toLocaleString("fr-FR")} €
          </span>
        </p>
      )}
    </div>
  );
}

export function BillingStatusChart() {
  const { data, isLoading } = useApiQuery(
    ["invoices-summary"],
    () => billingApi.listInvoices(1, 100),
    { refetchInterval: 30_000, retry: false }
  );

  const { chartData, total, overdueCount, overdueAmount } = useMemo(() => {
    const items = data?.items ?? [];
    const map: Record<string, { count: number; amount: number }> = {};

    for (const inv of items) {
      const s = inv.status as string;
      if (!map[s]) map[s] = { count: 0, amount: 0 };
      map[s].count++;
      map[s].amount += inv.amount ?? 0;
    }

    if (!items.length) {
      return {
        chartData: [
          { name: "Payée",      value: 8, color: C.green, amount: 24000 },
          { name: "En attente", value: 3, color: C.blue,  amount: 5400  },
          { name: "En retard",  value: 4, color: C.red,   amount: 7800  },
        ] as SliceData[],
        total: 15,
        overdueCount: 4,
        overdueAmount: 7800,
      };
    }

    const chartData: SliceData[] = Object.entries(map)
      .filter(([, v]) => v.count > 0)
      .map(([status, v]) => {
        const cfg = STATUS[status] ?? { label: status, color: C.muted };
        return { name: cfg.label, value: v.count, color: cfg.color, amount: v.amount };
      });

    const overdue = map["overdue"] ?? { count: 0, amount: 0 };
    return {
      chartData,
      total: items.length,
      overdueCount: overdue.count,
      overdueAmount: overdue.amount,
    };
  }, [data]);

  return (
    <div className="tablette-marbre flex flex-col gap-4"
      style={{ background: "rgba(5,5,5,0.82)", border: "1px solid var(--red-dark)" }}
    >
      {/* Header */}
      <div>
        <p className="font-cinzel text-xs tracking-[0.2em] uppercase" style={{ color: "var(--red-doge)" }}>
          État des factures
        </p>
        <p className="text-xs mt-0.5" style={{ color: "var(--gray-silver)" }}>
          Répartition par statut de paiement
        </p>
        {overdueCount > 0 ? (
          <div className="flex items-baseline gap-2 mt-2">
            <p className="text-3xl font-bold font-cinzel" style={{ color: "#FF1A1A", textShadow: "0 0 16px rgba(255,26,26,0.5)" }}>{overdueCount}</p>
            <p className="text-xs" style={{ color: "var(--gray-silver)" }}>
              en retard · {overdueAmount.toLocaleString("fr-FR")} €
            </p>
          </div>
        ) : (
          <p className="mt-2 text-2xl font-bold font-cinzel" style={{ color: "#D4A000" }}>Tout à jour ✓</p>
        )}
      </div>

      <div className="flex items-center gap-4">
          {/* Donut */}
          <ResponsiveContainer width={160} height={160}>
            <PieChart>
              <Pie
                data={chartData}
                cx="50%"
                cy="50%"
                innerRadius={48}
                outerRadius={72}
                paddingAngle={3}
                dataKey="value"
                startAngle={90}
                endAngle={-270}
              >
                {chartData.map((d, i) => (
                  <Cell key={i} fill={d.color} fillOpacity={0.9} />
                ))}
              </Pie>
              <Tooltip content={<CustomTooltip />} />
            </PieChart>
          </ResponsiveContainer>

          {/* Legend */}
          <div className="flex flex-col gap-2.5 flex-1">
            {chartData.map((d) => (
              <div key={d.name} className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span style={{ width: 8, height: 8, borderRadius: "50%", background: d.color, flexShrink: 0, display: "inline-block" }} />
                  <span className="text-xs" style={{ color: C.secondary }}>{d.name}</span>
                </div>
                <span className="text-xs font-semibold tabular-nums" style={{ color: C.primary }}>
                  {d.value}
                  <span style={{ color: C.muted, fontWeight: 400 }}> / {total}</span>
                </span>
              </div>
            ))}
          </div>
        </div>
    </div>
  );
}
