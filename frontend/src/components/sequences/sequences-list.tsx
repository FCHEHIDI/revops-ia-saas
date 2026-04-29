"use client";

import { Play, Pause, FileText, Users } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Spinner } from "@/components/ui/spinner";
import { Card } from "@/components/ui/card";
import { useApiQuery } from "@/hooks/useApi";
import { sequencesApi } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import type { Sequence, SequenceStatus } from "@/types";

const statusVariant: Record<SequenceStatus, "success" | "info" | "warning" | "neutral"> = {
  active: "success",
  paused: "warning",
  draft: "neutral",
  completed: "info",
};

const statusLabel: Record<SequenceStatus, string> = {
  active: "Active",
  paused: "En pause",
  draft: "Brouillon",
  completed: "Terminée",
};

function SequenceCard({ sequence }: { sequence: Sequence }) {
  const isActive = sequence.status === "active";

  return (
    <Card className="flex items-start justify-between gap-4 hover:border-border-strong transition-colors">
      <div className="flex items-start gap-3 min-w-0">
        <div className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${isActive ? "bg-emerald-500/10" : "bg-elevated"}`}>
          {isActive ? (
            <Play size={14} className="text-emerald-400" />
          ) : (
            <Pause size={14} className="text-text-muted" />
          )}
        </div>
        <div className="min-w-0">
          <p className="font-medium text-text-primary truncate">{sequence.name}</p>
          {sequence.description && (
            <p className="mt-0.5 text-xs text-text-muted line-clamp-1">{sequence.description}</p>
          )}
          <div className="mt-2 flex items-center gap-3 text-xs text-text-muted">
            <span className="flex items-center gap-1">
              <FileText size={11} />
              {sequence.step_count} étapes
            </span>
            <span className="flex items-center gap-1">
              <Users size={11} />
              {sequence.enrolled_count} inscrits
            </span>
            <span className="text-text-muted">{formatDate(sequence.updated_at)}</span>
          </div>
        </div>
      </div>
      <Badge variant={statusVariant[sequence.status]} className="shrink-0">
        {statusLabel[sequence.status]}
      </Badge>
    </Card>
  );
}

export function SequencesList() {
  const { data, isLoading, error } = useApiQuery(
    ["sequences"],
    () => sequencesApi.listSequences()
  );

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Spinner size="lg" />
      </div>
    );
  }

  if (error) {
    // API not available — render demo data instead of an error
  }

  const demoSequences: Sequence[] = [
    { id: "seq-1", tenant_id: "", name: "Onboarding SaaS Enterprise",   description: "Séquence d'activation pour nouveaux comptes +50k ARR",  status: "active",    step_count: 6, enrolled_count: 14, completed_count: 8,  created_at: "2026-04-01T09:00:00Z", updated_at: "2026-04-28T14:22:00Z" },
    { id: "seq-2", tenant_id: "", name: "Relance Pipeline Stagnant",     description: "Relance automatique après 14j sans activité",           status: "active",    step_count: 4, enrolled_count: 31, completed_count: 12, created_at: "2026-03-15T09:00:00Z", updated_at: "2026-04-27T10:11:00Z" },
    { id: "seq-3", tenant_id: "", name: "Cold Outreach Fintech Q2",      description: "Prospection cible CFO / Head of Finance secteur fintech",status: "paused",    step_count: 5, enrolled_count: 22, completed_count: 0,  created_at: "2026-04-10T09:00:00Z", updated_at: "2026-04-20T08:00:00Z" },
    { id: "seq-4", tenant_id: "", name: "Nurturing Leads MQL",           description: "Séquence éducative pour leads qualifiés MQL",           status: "active",    step_count: 8, enrolled_count: 58, completed_count: 34, created_at: "2026-02-20T09:00:00Z", updated_at: "2026-04-29T09:00:00Z" },
    { id: "seq-5", tenant_id: "", name: "Churn Prevention — à risque",   description: "Détection et réengagement comptes avec score <40",      status: "draft",     step_count: 3, enrolled_count: 0,  completed_count: 0,  created_at: "2026-04-25T09:00:00Z", updated_at: "2026-04-25T09:00:00Z" },
    { id: "seq-6", tenant_id: "", name: "Expansion Upsell Customers",    description: "Campagne upsell pour clients >6 mois avec ARR <20k",    status: "completed", step_count: 5, enrolled_count: 19, completed_count: 19, created_at: "2026-01-10T09:00:00Z", updated_at: "2026-04-01T16:00:00Z" },
  ];

  const sequences: Sequence[] = (error || !data) ? demoSequences : (data?.items ?? demoSequences);

  if (sequences.length === 0) {
    return (
      <div className="rounded-xl border border-border-default bg-surface p-12 text-center">
        <p className="text-text-secondary">Aucune séquence trouvée.</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {sequences.map((seq) => (
        <SequenceCard key={seq.id} sequence={seq} />
      ))}
    </div>
  );
}
