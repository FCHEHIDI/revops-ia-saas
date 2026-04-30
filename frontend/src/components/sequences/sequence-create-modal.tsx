"use client";

import { useState, useCallback } from "react";
import { X, Plus, Trash2, Mail, Phone, Linkedin, CheckSquare, Clock, ChevronRight, ChevronLeft } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { useApiMutation } from "@/hooks/useApi";
import { sequencesApi, type SequenceStepInput } from "@/lib/api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type StepType = "email" | "linkedin_message" | "call" | "task" | "wait";

interface DraftStep {
  id: string; // local only
  step_type: StepType;
  delay_days: number;
  delay_hours: number;
  subject: string;
  body_template: string;
}

interface Props {
  onClose: () => void;
  onCreated: () => void;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STEP_TYPES: { value: StepType; label: string; icon: React.ReactNode; color: string }[] = [
  { value: "email",            label: "Email",     icon: <Mail size={14} />,        color: "#50b4ff" },
  { value: "linkedin_message", label: "LinkedIn",  icon: <Linkedin size={14} />,    color: "#c88cff" },
  { value: "call",             label: "Appel",     icon: <Phone size={14} />,       color: "#78ffa0" },
  { value: "task",             label: "Tâche",     icon: <CheckSquare size={14} />, color: "#ff5050" },
  { value: "wait",             label: "Attente",   icon: <Clock size={14} />,       color: "#999999" },
];

const stepMeta = (type: StepType) => STEP_TYPES.find((s) => s.value === type) ?? STEP_TYPES[0];

function newStep(type: StepType = "email"): DraftStep {
  return {
    id: crypto.randomUUID(),
    step_type: type,
    delay_days: 1,
    delay_hours: 0,
    subject: "",
    body_template: "",
  };
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StepRow({
  step,
  index,
  total,
  onChange,
  onRemove,
}: {
  step: DraftStep;
  index: number;
  total: number;
  onChange: (id: string, patch: Partial<DraftStep>) => void;
  onRemove: (id: string) => void;
}) {
  const meta = stepMeta(step.step_type);
  const needsContent = step.step_type !== "wait";

  return (
    <div
      style={{
        background: "#111111",
        border: "1px solid #2a2a2a",
        borderRadius: 10,
        padding: "12px 14px",
        display: "flex",
        flexDirection: "column",
        gap: 10,
      }}
    >
      {/* Header row */}
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        {/* Step number */}
        <span
          style={{
            width: 22, height: 22, borderRadius: "50%",
            background: "#1a1a1a", border: "1px solid #3a3a3a",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 11, color: "#555555", flexShrink: 0,
          }}
        >
          {index + 1}
        </span>

        {/* Type selector */}
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", flex: 1 }}>
          {STEP_TYPES.map((t) => (
            <button
              key={t.value}
              onClick={() => onChange(step.id, { step_type: t.value })}
              style={{
                display: "flex", alignItems: "center", gap: 5,
                padding: "3px 10px", borderRadius: 6, fontSize: 12,
                border: step.step_type === t.value ? `1px solid ${t.color}40` : "1px solid #2a2a2a",
                background: step.step_type === t.value ? `${t.color}14` : "transparent",
                color: step.step_type === t.value ? t.color : "#555555",
                cursor: "pointer",
              }}
            >
              {t.icon} {t.label}
            </button>
          ))}
        </div>

        {/* Remove */}
        {total > 1 && (
          <button
            onClick={() => onRemove(step.id)}
            style={{ color: "#555555", background: "none", border: "none", cursor: "pointer", padding: 4 }}
          >
            <Trash2 size={14} />
          </button>
        )}
      </div>

      {/* Delay */}
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ fontSize: 12, color: "#555555" }}>Délai :</span>
        <input
          type="number"
          min={0}
          value={step.delay_days}
          onChange={(e) => onChange(step.id, { delay_days: Math.max(0, Number(e.target.value)) })}
          style={inputStyle}
        />
        <span style={{ fontSize: 12, color: "#555555" }}>j</span>
        <input
          type="number"
          min={0}
          max={23}
          value={step.delay_hours}
          onChange={(e) => onChange(step.id, { delay_hours: Math.min(23, Math.max(0, Number(e.target.value))) })}
          style={{ ...inputStyle, width: 52 }}
        />
        <span style={{ fontSize: 12, color: "#555555" }}>h</span>
      </div>

      {/* Content fields */}
      {needsContent && (
        <>
          {(step.step_type === "email" || step.step_type === "linkedin_message") && (
            <input
              type="text"
              placeholder="Objet…"
              value={step.subject}
              onChange={(e) => onChange(step.id, { subject: e.target.value })}
              style={{ ...inputStyle, width: "100%" }}
            />
          )}
          <textarea
            placeholder={step.step_type === "task" ? "Description de la tâche…" : "Corps du message…"}
            value={step.body_template}
            rows={3}
            onChange={(e) => onChange(step.id, { body_template: e.target.value })}
            style={{
              ...inputStyle,
              width: "100%",
              resize: "vertical",
              fontFamily: "inherit",
              minHeight: 64,
            }}
          />
        </>
      )}
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  background: "#0a0a0a",
  border: "1px solid #2a2a2a",
  borderRadius: 6,
  padding: "4px 10px",
  fontSize: 12,
  color: "#f5f5f5",
  width: 64,
  outline: "none",
};

// ---------------------------------------------------------------------------
// Modal
// ---------------------------------------------------------------------------

export function SequenceCreateModal({ onClose, onCreated }: Props) {
  const { user } = useAuth();

  // Step 1 fields
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  // Step 2 fields
  const [steps, setSteps] = useState<DraftStep[]>([newStep("email")]);

  // Wizard page: 0 = info, 1 = steps
  const [page, setPage] = useState(0);

  // Mutation
  const mutation = useApiMutation(
    (vars: Parameters<typeof sequencesApi.createSequence>[0]) =>
      sequencesApi.createSequence(vars),
    [["sequences"]]
  );

  const addStep = useCallback(() => setSteps((prev) => [...prev, newStep("email")]), []);

  const updateStep = useCallback((id: string, patch: Partial<DraftStep>) => {
    setSteps((prev) => prev.map((s) => (s.id === id ? { ...s, ...patch } : s)));
  }, []);

  const removeStep = useCallback((id: string) => {
    setSteps((prev) => prev.filter((s) => s.id !== id));
  }, []);

  const handleSubmit = async () => {
    if (!user) return;
    const payload: SequenceStepInput[] = steps.map(({ step_type, delay_days, delay_hours, subject, body_template }) => ({
      step_type,
      delay_days,
      delay_hours,
      subject: subject || undefined,
      body_template: body_template || undefined,
    }));
    await mutation.mutateAsync({
      tenant_id: user.tenant_id,
      user_id: user.id,
      name: name.trim(),
      description: description.trim() || undefined,
      steps: payload,
    });
    onCreated();
    onClose();
  };

  const page1Valid = name.trim().length >= 2;

  return (
    /* Backdrop */
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, zIndex: 50,
        background: "rgba(0,0,0,0.75)", backdropFilter: "blur(4px)",
        display: "flex", alignItems: "center", justifyContent: "center",
        padding: 16,
      }}
    >
      {/* Panel */}
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "#0d001a",
          border: "1px solid #2a2a2a",
          borderRadius: 14,
          width: "100%",
          maxWidth: 560,
          maxHeight: "90vh",
          overflow: "hidden",
          display: "flex",
          flexDirection: "column",
          boxShadow: "0 24px 80px rgba(0,0,0,0.9)",
        }}
      >
        {/* Header */}
        <div style={{ padding: "18px 20px 14px", borderBottom: "1px solid #1f1f1f", display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ flex: 1 }}>
            <p style={{ fontSize: 15, fontWeight: 600, color: "#f5f5f5", margin: 0 }}>
              Nouvelle séquence
            </p>
            <p style={{ fontSize: 12, color: "#555555", margin: 0 }}>
              {page === 0 ? "Étape 1/2 — Informations générales" : "Étape 2/2 — Construction des étapes"}
            </p>
          </div>
          {/* Progress dots */}
          <div style={{ display: "flex", gap: 6 }}>
            {[0, 1].map((i) => (
              <span
                key={i}
                style={{
                  width: 6, height: 6, borderRadius: "50%",
                  background: i <= page ? "#2979ff" : "#2a2a2a",
                  transition: "background 0.2s",
                }}
              />
            ))}
          </div>
          <button
            onClick={onClose}
            style={{ color: "#555555", background: "none", border: "none", cursor: "pointer", padding: 4 }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflowY: "auto", padding: "20px" }}>
          {page === 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <div>
                <label style={{ fontSize: 12, color: "#999999", display: "block", marginBottom: 6 }}>
                  Nom de la séquence <span style={{ color: "#ff5050" }}>*</span>
                </label>
                <input
                  autoFocus
                  type="text"
                  placeholder="ex. Cold Outreach Q3 Fintech"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  style={{
                    ...inputStyle,
                    width: "100%",
                    padding: "8px 12px",
                    fontSize: 14,
                    borderRadius: 8,
                  }}
                />
              </div>
              <div>
                <label style={{ fontSize: 12, color: "#999999", display: "block", marginBottom: 6 }}>
                  Description <span style={{ color: "#555555" }}>(optionnel)</span>
                </label>
                <textarea
                  placeholder="Objectif, audience cible…"
                  value={description}
                  rows={3}
                  onChange={(e) => setDescription(e.target.value)}
                  style={{
                    ...inputStyle,
                    width: "100%",
                    padding: "8px 12px",
                    fontSize: 13,
                    borderRadius: 8,
                    resize: "vertical",
                    minHeight: 72,
                    fontFamily: "inherit",
                  }}
                />
              </div>
            </div>
          )}

          {page === 1 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {steps.map((step, idx) => (
                <StepRow
                  key={step.id}
                  step={step}
                  index={idx}
                  total={steps.length}
                  onChange={updateStep}
                  onRemove={removeStep}
                />
              ))}
              <button
                onClick={addStep}
                style={{
                  display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
                  padding: "9px 0", borderRadius: 8,
                  border: "1px dashed #2a2a2a",
                  background: "transparent",
                  color: "#555555", fontSize: 13, cursor: "pointer",
                }}
              >
                <Plus size={14} /> Ajouter une étape
              </button>
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{
          padding: "14px 20px",
          borderTop: "1px solid #1f1f1f",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}>
          {page === 0 ? (
            <button
              onClick={onClose}
              style={{ fontSize: 13, color: "#555555", background: "none", border: "none", cursor: "pointer" }}
            >
              Annuler
            </button>
          ) : (
            <button
              onClick={() => setPage(0)}
              style={{
                display: "flex", alignItems: "center", gap: 5,
                fontSize: 13, color: "#999999", background: "none", border: "none", cursor: "pointer",
              }}
            >
              <ChevronLeft size={15} /> Retour
            </button>
          )}

          {page === 0 ? (
            <button
              onClick={() => setPage(1)}
              disabled={!page1Valid}
              style={{
                display: "flex", alignItems: "center", gap: 6,
                padding: "8px 18px", borderRadius: 8, fontSize: 13, fontWeight: 500,
                background: page1Valid ? "#2979ff" : "#1a1a1a",
                color: page1Valid ? "#fff" : "#555555",
                border: "none", cursor: page1Valid ? "pointer" : "not-allowed",
                transition: "background 0.2s",
              }}
            >
              Suivant <ChevronRight size={15} />
            </button>
          ) : (
            <button
              onClick={handleSubmit}
              disabled={mutation.isPending || steps.length === 0}
              style={{
                display: "flex", alignItems: "center", gap: 6,
                padding: "8px 18px", borderRadius: 8, fontSize: 13, fontWeight: 500,
                background: mutation.isPending ? "#1a1a1a" : "#2979ff",
                color: mutation.isPending ? "#555555" : "#fff",
                border: "none", cursor: mutation.isPending ? "not-allowed" : "pointer",
                transition: "background 0.2s",
              }}
            >
              {mutation.isPending ? "Création…" : `Créer (${steps.length} étape${steps.length > 1 ? "s" : ""})`}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
