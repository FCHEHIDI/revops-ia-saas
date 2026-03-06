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
    <Card className="flex items-start justify-between gap-4 hover:border-slate-600 transition-colors">
      <div className="flex items-start gap-3 min-w-0">
        <div className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${isActive ? "bg-emerald-500/10" : "bg-slate-700"}`}>
          {isActive ? (
            <Play size={14} className="text-emerald-400" />
          ) : (
            <Pause size={14} className="text-slate-500" />
          )}
        </div>
        <div className="min-w-0">
          <p className="font-medium text-slate-100 truncate">{sequence.name}</p>
          {sequence.description && (
            <p className="mt-0.5 text-xs text-slate-500 line-clamp-1">{sequence.description}</p>
          )}
          <div className="mt-2 flex items-center gap-3 text-xs text-slate-500">
            <span className="flex items-center gap-1">
              <FileText size={11} />
              {sequence.step_count} étapes
            </span>
            <span className="flex items-center gap-1">
              <Users size={11} />
              {sequence.enrolled_count} inscrits
            </span>
            <span className="text-slate-600">{formatDate(sequence.updated_at)}</span>
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
    return (
      <div className="rounded-lg border border-red-800/50 bg-red-900/10 p-6 text-center text-sm text-red-400">
        Erreur lors du chargement des séquences : {error.message}
      </div>
    );
  }

  const sequences: Sequence[] = data?.items ?? [];

  if (sequences.length === 0) {
    return (
      <div className="rounded-xl border border-slate-700 bg-slate-800 p-12 text-center">
        <p className="text-slate-400">Aucune séquence trouvée.</p>
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
