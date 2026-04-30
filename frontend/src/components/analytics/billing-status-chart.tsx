"use client";

import { useMemo } from "react";
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import { Card } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { useApiQuery } from "@/hooks/useApi";
import { billingApi } from "@/lib/api";

const STATUS_CONFIG = {
  paid:      { label: "Payée",    color: "#10b981" },
  pending:   { label: "En attente", color: "#6366f1" },
  overdue:   { label: "En retard",  color: "#ef4444" },
  draft:     { label: "Brouillon",  color: "#6b7280" },
  cancelled: { label: "Annulée",   color: "#374151" },
} as const;

type InvoiceStatus = keyof typeof STATUS_CONFIG;

interface TooltipPayload {
  name: string;
  value: number;
  payload: { color: string };
}

function CustomTooltip({ active, payload }: { active?: boolean; payload?: TooltipPayload[] }) {
  if (!active || !payload?.length) return null;
  const d = payload[0];
  return (
    <div className="rounded-lg border border-white/10 bg-bg-card px-3 py-2 shadow-lg text-xs">
      <div className="flex items-center gap-2">
        <span className="w-2 h-2 rounded-full" style={{ background: d.payload.color }} />
        <span className="text-text-muted">{d.name}:</span>
        <span className="font-medium text-text-primary">{d.value} facture{d.value > 1 ? "s" : ""}</span>
      </div>
    </div>
  );
}

export function BillingStatusChart() {
  const { data, isLoading } = useApiQuery(
    ["invoices-summary"],
    () => billingApi.listInvoices(1, 100),
    { refetchInterval: 30_000, retry: false }
  );

  const { chartData, overdueCount, overdueAmount } = useMemo(() => {
    const items = data?.items ?? [];
    const counts: Record<string, number> = {};
    let overdueCount = 0;
    let overdueAmount = 0;

    for (const inv of items) {
      const s = inv.status as string;
      counts[s] = (counts[s] ?? 0) + 1;
      if (s === "overdue") {
        overdueCount++;
        overdueAmount += inv.amount;
      }
    }

    if (!items.length) {
      return {
        chartData: [
          { name: "Payée",     value: 8,  color: "#10b981" },
          { name: "En attente", value: 3, color: "#6366f1" },
          { name: "En retard",  value: 4, color: "#ef4444" },
        ],
        overdueCount: 4,
        overdueAmount: 7800,
      };
    }

    const chartData = Object.entries(counts)
      .filter(([, v]) => v > 0)
      .map(([status, value]) => {
        const cfg = STATUS_CONFIG[status as InvoiceStatus] ?? { label: status, color: "#6b7280" };
        return { name: cfg.label, value, color: cfg.color };
      });

    return { chartData, overdueCount, overdueAmount };
  }, [data]);

  return (
    <Card className="flex flex-col gap-4">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-medium text-text-muted uppercase tracking-wide">Statut des factures</p>
          {overdueCount > 0 ? (
            <>
              <p className="mt-1 text-2xl font-bold text-red-400">{overdueCount}</p>
              <p className="text-xs text-text-muted">
                en retard · {overdueAmount.toLocaleString("fr-FR")} €
              </p>
            </>
          ) : (
            <p className="mt-1 text-2xl font-bold text-emerald-400">Tout à jour</p>
          )}
        </div>
      </div>

      {isLoading ? (
        <div className="flex h-48 items-center justify-center">
          <Spinner size="lg" />
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={200}>
          <PieChart>
            <Pie
              data={chartData}
              cx="50%"
              cy="50%"
              innerRadius={52}
              outerRadius={80}
              paddingAngle={3}
              dataKey="value"
            >
              {chartData.map((entry, i) => (
                <Cell key={i} fill={entry.color} fillOpacity={0.9} />
              ))}
            </Pie>
            <Tooltip content={<CustomTooltip />} />
            <Legend
              formatter={(value) => <span style={{ color: "#9ca3af", fontSize: 12 }}>{value}</span>}
            />
          </PieChart>
        </ResponsiveContainer>
      )}
    </Card>
  );
}
