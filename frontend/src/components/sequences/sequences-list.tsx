"use client";

import { useState } from "react";
import { Play, Pause, FileText, Users } from "lucide-react";
import { Spinner } from "@/components/ui/spinner";
import { useApiQuery, useApiMutation } from "@/hooks/useApi";
import { useAuth } from "@/hooks/useAuth";
import { sequencesApi } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { SequenceCreateModal } from "./sequence-create-modal";
import type { Sequence, SequenceStatus } from "@/types";

/* ── Palette statut vénitienne ── */
const STATUS_CFG: Record<SequenceStatus, { label: string; color: string; bg: string; border: string; glyph: string }> = {
  active:    { label: "Active",    color: "#9B4FD4", bg: "rgba(155,79,212,0.13)",  border: "rgba(155,79,212,0.38)", glyph: "▶" },
  paused:    { label: "En pause",  color: "#C07000", bg: "rgba(192,112,0,0.12)",  border: "rgba(192,112,0,0.35)",  glyph: "◐" },
  draft:     { label: "Brouillon", color: "#7A5555", bg: "rgba(122,85,85,0.10)",  border: "rgba(122,85,85,0.30)",  glyph: "◎" },
  completed: { label: "Terminée",  color: "#D4A000", bg: "rgba(212,160,0,0.12)",  border: "rgba(212,160,0,0.35)",  glyph: "✦" },
};

function StatusBadge({ status }: { status: SequenceStatus }) {
  const cfg = STATUS_CFG[status];
  return (
    <span
      className="inline-flex items-center gap-1 rounded px-2 py-0.5 font-cinzel text-xs tracking-[0.1em] uppercase shrink-0"
      style={{ color: cfg.color, background: cfg.bg, border: `1px solid ${cfg.border}` }}
    >
      <span style={{ fontSize: "0.55rem" }}>{cfg.glyph}</span>
      {cfg.label}
    </span>
  );
}

function SequenceCard({ sequence }: { sequence: Sequence }) {
  const { user } = useAuth();
  const [hovered, setHovered] = useState(false);
  const isActive = sequence.status === "active";
  const canToggle = sequence.status === "active" || sequence.status === "paused";

  const toggleMutation = useApiMutation(
    (vars: Parameters<typeof sequencesApi.updateSequenceStatus>[0]) =>
      sequencesApi.updateSequenceStatus(vars),
    [["sequences"]]
  );

  const handleToggle = () => {
    if (!user || !canToggle || toggleMutation.isPending) return;
    toggleMutation.mutate({
      tenant_id: user.tenant_id,
      user_id: user.id,
      sequence_id: sequence.id,
      status: isActive ? "paused" : "active",
    });
  };

  /* barre de progression enrolled/step_count */
  const progress = sequence.enrolled_count > 0
    ? Math.round((sequence.completed_count / sequence.enrolled_count) * 100)
    : 0;

  return (
    <div
      className="tablette-marbre"
      style={{
        padding: "14px 18px",
        borderColor: hovered ? "rgba(155,79,212,0.35)" : "var(--red-dark)",
        transition: "border-color 0.2s ease, background 0.2s ease",
        background: hovered ? "rgba(155,79,212,0.05)" : undefined,
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div className="flex items-start justify-between gap-4">
        {/* Bouton toggle + infos */}
        <div className="flex items-start gap-3 min-w-0">
          {/* Toggle */}
          <button
            onClick={handleToggle}
            disabled={!canToggle || toggleMutation.isPending}
            title={canToggle ? (isActive ? "Mettre en pause" : "Activer") : undefined}
            style={{
              marginTop: 2,
              width: 32, height: 32, borderRadius: 8, flexShrink: 0,
              display: "flex", alignItems: "center", justifyContent: "center",
              border: `1px solid ${isActive ? "rgba(155,79,212,0.4)" : "var(--red-dark)"}`,
              background: isActive ? "rgba(155,79,212,0.12)" : "rgba(138,0,0,0.10)",
              cursor: canToggle ? "pointer" : "default",
              transition: "all 0.15s ease",
            }}
          >
            {toggleMutation.isPending ? (
              <Spinner size="sm" />
            ) : isActive ? (
              <Play size={13} style={{ color: "#9B4FD4" }} />
            ) : (
              <Pause size={13} style={{ color: "var(--gray-silver)" }} />
            )}
          </button>

          {/* Nom + description */}
          <div className="min-w-0">
            <p
              className="font-cinzel font-medium truncate"
              style={{ color: "var(--white-spectral)", fontSize: "0.9rem", letterSpacing: "0.03em" }}
            >
              {sequence.name}
            </p>
            {sequence.description && (
              <p className="mt-0.5 text-xs line-clamp-1" style={{ color: "var(--gray-silver)", fontFamily: "var(--font-body)" }}>
                {sequence.description}
              </p>
            )}

            {/* Méta-infos */}
            <div className="mt-2 flex items-center gap-4 text-xs" style={{ color: "var(--gray-silver)", fontFamily: "var(--font-mono)" }}>
              <span className="flex items-center gap-1">
                <FileText size={11} style={{ color: "var(--red-doge)" }} />
                {sequence.step_count} étapes
              </span>
              <span className="flex items-center gap-1">
                <Users size={11} style={{ color: "#9B4FD4" }} />
                {sequence.enrolled_count} inscrits
              </span>
              <span style={{ color: "var(--red-dark)", fontSize: "0.68rem" }}>
                {formatDate(sequence.updated_at)}
              </span>
            </div>
          </div>
        </div>

        {/* Statut badge */}
        <StatusBadge status={sequence.status} />
      </div>

      {/* ── Barre de progression ── */}
      {sequence.enrolled_count > 0 && (
        <div className="mt-3 flex items-center gap-2">
          <div style={{ flex: 1, height: 3, borderRadius: 2, background: "rgba(138,0,0,0.20)" }}>
            <div
              style={{
                width: `${progress}%`,
                height: "100%",
                borderRadius: 2,
                background: sequence.status === "completed"
                  ? "linear-gradient(to right, #C07000, #D4A000)"
                  : "linear-gradient(to right, #6B2080, #9B4FD4)",
                transition: "width 0.4s ease",
              }}
            />
          </div>
          <span style={{ fontSize: "0.65rem", color: "var(--gray-silver)", fontFamily: "var(--font-mono)", flexShrink: 0 }}>
            {sequence.completed_count}/{sequence.enrolled_count}
          </span>
        </div>
      )}
    </div>
  );
}

export function SequencesList() {
  const [showModal, setShowModal] = useState(false);
  const { data, isLoading, error, refetch } = useApiQuery(
    ["sequences"],
    () => sequencesApi.listSequences()
  );

  const demoSequences: Sequence[] = [
    { id: "seq-1", tenant_id: "", name: "Onboarding SaaS Enterprise",   description: "Séquence d'activation pour nouveaux comptes +50k ARR",   status: "active",    step_count: 6, enrolled_count: 14, completed_count: 8,  created_at: "2026-04-01T09:00:00Z", updated_at: "2026-04-28T14:22:00Z" },
    { id: "seq-2", tenant_id: "", name: "Relance Pipeline Stagnant",     description: "Relance automatique après 14j sans activité",            status: "active",    step_count: 4, enrolled_count: 31, completed_count: 12, created_at: "2026-03-15T09:00:00Z", updated_at: "2026-04-27T10:11:00Z" },
    { id: "seq-3", tenant_id: "", name: "Cold Outreach Fintech Q2",      description: "Prospection cible CFO / Head of Finance secteur fintech", status: "paused",    step_count: 5, enrolled_count: 22, completed_count: 0,  created_at: "2026-04-10T09:00:00Z", updated_at: "2026-04-20T08:00:00Z" },
    { id: "seq-4", tenant_id: "", name: "Nurturing Leads MQL",           description: "Séquence éducative pour leads qualifiés MQL",            status: "active",    step_count: 8, enrolled_count: 58, completed_count: 34, created_at: "2026-02-20T09:00:00Z", updated_at: "2026-04-29T09:00:00Z" },
    { id: "seq-5", tenant_id: "", name: "Churn Prevention — à risque",   description: "Détection et réengagement comptes avec score <40",       status: "draft",     step_count: 3, enrolled_count: 0,  completed_count: 0,  created_at: "2026-04-25T09:00:00Z", updated_at: "2026-04-25T09:00:00Z" },
    { id: "seq-6", tenant_id: "", name: "Expansion Upsell Customers",    description: "Campagne upsell pour clients >6 mois avec ARR <20k",     status: "completed", step_count: 5, enrolled_count: 19, completed_count: 19, created_at: "2026-01-10T09:00:00Z", updated_at: "2026-04-01T16:00:00Z" },
  ];

  const sequences: Sequence[] = (error || !data) ? demoSequences : (data?.items ?? demoSequences);
  const activeCount = sequences.filter(s => s.status === "active").length;

  return (
    <>
      {/* ── En-tête ── */}
      <div className="mb-5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="font-cinzel text-sm font-medium" style={{ color: "var(--white-spectral)", letterSpacing: "0.05em" }}>
            {sequences.length} rituels
          </span>
          {activeCount > 0 && (
            <span
              className="inline-flex items-center gap-1 rounded px-2 py-0.5 font-cinzel text-xs tracking-[0.1em]"
              style={{ color: "#9B4FD4", background: "rgba(155,79,212,0.12)", border: "1px solid rgba(155,79,212,0.35)" }}
            >
              ▶ {activeCount} actif{activeCount > 1 ? "s" : ""}
            </span>
          )}
        </div>

        {/* Bouton créer */}
        <button
          onClick={() => setShowModal(true)}
          className="font-cinzel text-xs tracking-[0.15em] uppercase"
          style={{
            display: "flex", alignItems: "center", gap: 8,
            padding: "8px 18px", borderRadius: 6,
            background: "rgba(155,79,212,0.12)",
            border: "1px solid rgba(155,79,212,0.40)",
            color: "#9B4FD4",
            cursor: "pointer",
            transition: "all 0.15s ease",
          }}
          onMouseEnter={e => {
            (e.currentTarget as HTMLButtonElement).style.background = "rgba(155,79,212,0.22)";
            (e.currentTarget as HTMLButtonElement).style.boxShadow = "0 0 14px rgba(155,79,212,0.25)";
          }}
          onMouseLeave={e => {
            (e.currentTarget as HTMLButtonElement).style.background = "rgba(155,79,212,0.12)";
            (e.currentTarget as HTMLButtonElement).style.boxShadow = "none";
          }}
        >
          <span style={{ fontSize: "0.9rem", lineHeight: 1 }}>✦</span>
          Créer un rituel
        </button>
      </div>

      {/* ── Séparateur ── */}
      <div className="flex items-center gap-3 mb-5">
        <div style={{ flex: 1, height: 1, background: "linear-gradient(to right, transparent, var(--red-dark))" }} />
        <span className="font-cinzel text-xs tracking-[0.35em] uppercase" style={{ color: "var(--red-doge)" }}>
          ⚜ Registre des Séquences
        </span>
        <div style={{ flex: 1, height: 1, background: "linear-gradient(to left, transparent, var(--red-dark))" }} />
      </div>

      {/* ── Liste ── */}
      {isLoading ? (
        <div className="flex items-center justify-center py-16">
          <Spinner size="lg" />
        </div>
      ) : sequences.length === 0 ? (
        <div className="tablette-marbre p-12 text-center">
          <p className="font-cinzel text-sm tracking-[0.2em]" style={{ color: "var(--gray-silver)" }}>
            Aucun rituel dans les archives. Créez-en un !
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {sequences.map((seq) => (
            <SequenceCard key={seq.id} sequence={seq} />
          ))}
        </div>
      )}

      {/* ── Modal ── */}
      {showModal && (
        <SequenceCreateModal
          onClose={() => setShowModal(false)}
          onCreated={() => { refetch(); }}
        />
      )}
    </>
  );
}
