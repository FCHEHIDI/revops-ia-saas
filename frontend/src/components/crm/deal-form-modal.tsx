"use client";

import { useState } from "react";
import { X } from "lucide-react";
import { useApiMutation, useApiQuery } from "@/hooks/useApi";
import { crmApi } from "@/lib/api";
import type { DealCreate, DealStage, Account } from "@/types";

interface DealFormModalProps {
  onClose: () => void;
  /** Pré-sélectionner un compte */
  preselectedAccountId?: string;
}

const STAGE_OPTIONS: { value: DealStage; label: string }[] = [
  { value: "prospecting",   label: "Prospection" },
  { value: "qualification", label: "Qualification" },
  { value: "proposal",      label: "Proposition" },
  { value: "negotiation",   label: "Négociation" },
  { value: "closing",       label: "Closing" },
  { value: "won",           label: "Gagné" },
  { value: "lost",          label: "Perdu" },
];

const FIELD_STYLE = {
  width: "100%",
  background: "rgba(8,8,8,0.8)",
  border: "1px solid rgba(138,0,0,0.35)",
  borderRadius: 4,
  padding: "8px 12px",
  color: "var(--white-spectral)",
  fontFamily: "var(--font-body)",
  fontSize: "0.8rem",
  outline: "none",
  boxSizing: "border-box" as const,
};

const LABEL_STYLE = {
  display: "block",
  fontSize: "0.65rem",
  textTransform: "uppercase" as const,
  letterSpacing: "0.12em",
  color: "var(--red-doge)",
  fontFamily: "var(--font-cinzel, 'Cinzel', serif)",
  marginBottom: 4,
};

export function DealFormModal({ onClose, preselectedAccountId }: DealFormModalProps) {
  const [form, setForm] = useState<DealCreate>({
    account_id:  preselectedAccountId ?? "",
    title:       "",
    stage:       "prospecting",
    amount:      undefined,
    currency:    "EUR",
    close_date:  "",
    probability: undefined,
    notes:       "",
  });
  const [error, setError] = useState<string | null>(null);

  const { data: accountsData } = useApiQuery(
    ["accounts", "dropdown"],
    () => crmApi.listAccounts({ limit: 100 })
  );
  const accounts: Account[] = accountsData?.items ?? [];

  const createMutation = useApiMutation(
    (data: DealCreate) => crmApi.createDeal(data),
    [["deals"]]
  );

  function set<K extends keyof DealCreate>(field: K, value: DealCreate[K]) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    const payload: DealCreate = {
      account_id: form.account_id,
      title:      form.title.trim(),
      stage:      form.stage,
      currency:   form.currency || "EUR",
      ...(form.amount      != null ? { amount:      form.amount }      : {}),
      ...(form.close_date?.trim() ? { close_date:  form.close_date }   : {}),
      ...(form.probability != null ? { probability: form.probability }  : {}),
      ...(form.notes?.trim()       ? { notes:       form.notes.trim() } : {}),
    };

    try {
      await createMutation.mutateAsync(payload);
      onClose();
    } catch (err) {
      setError((err as Error).message ?? "Une erreur est survenue");
    }
  }

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 200,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "rgba(0,0,0,0.75)",
        backdropFilter: "blur(4px)",
      }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        className="tablette-marbre"
        style={{ width: "100%", maxWidth: 520, padding: "28px 32px", position: "relative" }}
      >
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 24 }}>
          <div>
            <p
              className="font-cinzel"
              style={{ fontSize: "0.6rem", letterSpacing: "0.3em", textTransform: "uppercase", color: "var(--red-doge)", marginBottom: 2 }}
            >
              Nouveau
            </p>
            <h2
              className="font-cinzel"
              style={{ fontSize: "1.2rem", fontWeight: 700, color: "var(--white-spectral)" }}
            >
              Opportunité
            </h2>
          </div>
          <button
            onClick={onClose}
            style={{ background: "transparent", border: "none", cursor: "pointer", color: "var(--gray-silver)", padding: 4 }}
          >
            <X size={16} />
          </button>
        </div>

        <div style={{ height: 1, background: "linear-gradient(90deg, var(--red-dark), transparent)", marginBottom: 24 }} />

        <form onSubmit={handleSubmit}>
          {/* Titre */}
          <div style={{ marginBottom: 16 }}>
            <label style={LABEL_STYLE}>Titre *</label>
            <input
              required
              type="text"
              value={form.title}
              onChange={(e) => set("title", e.target.value)}
              style={FIELD_STYLE}
              placeholder="Contrat annuel NovaTech"
            />
          </div>

          {/* Compte */}
          <div style={{ marginBottom: 16 }}>
            <label style={LABEL_STYLE}>Compte *</label>
            <select
              required
              value={form.account_id}
              onChange={(e) => set("account_id", e.target.value)}
              style={FIELD_STYLE}
            >
              <option value="">— Sélectionner un compte —</option>
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>{a.name}</option>
              ))}
            </select>
          </div>

          {/* Stage / Probabilité */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
            <div>
              <label style={LABEL_STYLE}>Étape *</label>
              <select
                required
                value={form.stage}
                onChange={(e) => set("stage", e.target.value as DealStage)}
                style={FIELD_STYLE}
              >
                {STAGE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label style={LABEL_STYLE}>Probabilité (%)</label>
              <input
                type="number"
                min={0}
                max={100}
                value={form.probability ?? ""}
                onChange={(e) => set("probability", e.target.value ? Number(e.target.value) : undefined)}
                style={FIELD_STYLE}
                placeholder="75"
              />
            </div>
          </div>

          {/* Montant / Date */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
            <div>
              <label style={LABEL_STYLE}>Montant (€)</label>
              <input
                type="number"
                min={0}
                value={form.amount ?? ""}
                onChange={(e) => set("amount", e.target.value ? Number(e.target.value) : undefined)}
                style={FIELD_STYLE}
                placeholder="12 000"
              />
            </div>
            <div>
              <label style={LABEL_STYLE}>Date de clôture</label>
              <input
                type="date"
                value={form.close_date ?? ""}
                onChange={(e) => set("close_date", e.target.value)}
                style={FIELD_STYLE}
              />
            </div>
          </div>

          {/* Notes */}
          <div style={{ marginBottom: 24 }}>
            <label style={LABEL_STYLE}>Notes</label>
            <textarea
              value={form.notes ?? ""}
              onChange={(e) => set("notes", e.target.value)}
              style={{ ...FIELD_STYLE, resize: "vertical", minHeight: 72 }}
              placeholder="Contexte, prochaines étapes…"
            />
          </div>

          {/* Error */}
          {error && (
            <div
              style={{
                background: "rgba(192,0,0,0.12)",
                border: "1px solid rgba(192,0,0,0.4)",
                borderRadius: 4,
                padding: "8px 12px",
                marginBottom: 16,
                fontSize: "0.75rem",
                color: "var(--red-doge)",
                fontFamily: "var(--font-body)",
              }}
            >
              ⚠ {error}
            </div>
          )}

          {/* Actions */}
          <div style={{ display: "flex", gap: 12, justifyContent: "flex-end" }}>
            <button
              type="button"
              onClick={onClose}
              disabled={createMutation.isPending}
              className="font-cinzel"
              style={{
                background: "transparent",
                border: "1px solid rgba(138,0,0,0.3)",
                borderRadius: 4,
                padding: "8px 20px",
                color: "var(--gray-silver)",
                cursor: "pointer",
                fontSize: "0.7rem",
                letterSpacing: "0.1em",
                textTransform: "uppercase",
              }}
            >
              Annuler
            </button>
            <button
              type="submit"
              disabled={createMutation.isPending}
              className="font-cinzel"
              style={{
                background: createMutation.isPending ? "rgba(138,0,0,0.2)" : "rgba(138,0,0,0.35)",
                border: "1px solid var(--red-dark)",
                borderRadius: 4,
                padding: "8px 20px",
                color: createMutation.isPending ? "var(--gray-silver)" : "var(--white-spectral)",
                cursor: createMutation.isPending ? "not-allowed" : "pointer",
                fontSize: "0.7rem",
                letterSpacing: "0.1em",
                textTransform: "uppercase",
                boxShadow: createMutation.isPending ? "none" : "var(--glow-red)",
                transition: "all 0.2s",
              }}
            >
              {createMutation.isPending ? "Enregistrement…" : "Créer"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
