"use client";

import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { useApiMutation } from "@/hooks/useApi";
import { crmApi } from "@/lib/api";
import type { Contact, ContactCreate, ContactStatus } from "@/types";

interface ContactFormModalProps {
  /** Null = création, Contact = édition */
  contact?: Contact | null;
  onClose: () => void;
  onSuccess?: (contact: Contact) => void;
}

const STATUS_OPTIONS: { value: ContactStatus; label: string }[] = [
  { value: "active",   label: "Actif" },
  { value: "lead",     label: "Lead" },
  { value: "customer", label: "Client" },
  { value: "inactive", label: "Inactif" },
  { value: "churned",  label: "Churné" },
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

export function ContactFormModal({ contact, onClose, onSuccess }: ContactFormModalProps) {
  const isEdit = !!contact;

  const [form, setForm] = useState<ContactCreate>({
    first_name: contact?.first_name ?? "",
    last_name:  contact?.last_name  ?? "",
    email:      contact?.email      ?? "",
    phone:      contact?.phone      ?? "",
    job_title:  contact?.job_title  ?? "",
    status:     (contact?.status as ContactStatus) ?? "active",
    account_id: contact?.account_id ?? "",
  });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (contact) {
      setForm({
        first_name: contact.first_name,
        last_name:  contact.last_name,
        email:      contact.email,
        phone:      contact.phone      ?? "",
        job_title:  contact.job_title  ?? "",
        status:     contact.status as ContactStatus,
        account_id: contact.account_id ?? "",
      });
    }
  }, [contact]);

  const createMutation = useApiMutation(
    (data: ContactCreate) => crmApi.createContact(data),
    [["contacts"]]
  );
  const updateMutation = useApiMutation(
    (data: ContactCreate) => crmApi.updateContact(contact!.id, data),
    [["contacts"], ["contact", contact?.id ?? ""]]
  );

  const isPending = createMutation.isPending || updateMutation.isPending;

  function set(field: keyof ContactCreate, value: string) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    const payload: ContactCreate = {
      first_name: form.first_name.trim(),
      last_name:  form.last_name.trim(),
      email:      form.email.trim(),
      status:     form.status,
      ...(form.phone?.trim()     ? { phone:      form.phone.trim()     } : {}),
      ...(form.job_title?.trim() ? { job_title:  form.job_title.trim() } : {}),
      ...(form.account_id?.trim() ? { account_id: form.account_id.trim() } : {}),
    };

    try {
      let result: Contact;
      if (isEdit) {
        result = await updateMutation.mutateAsync(payload);
      } else {
        result = await createMutation.mutateAsync(payload);
      }
      onSuccess?.(result);
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
        style={{ width: "100%", maxWidth: 480, padding: "28px 32px", position: "relative" }}
      >
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 24 }}>
          <div>
            <p
              className="font-cinzel"
              style={{ fontSize: "0.6rem", letterSpacing: "0.3em", textTransform: "uppercase", color: "var(--red-doge)", marginBottom: 2 }}
            >
              {isEdit ? "Modifier" : "Nouveau"}
            </p>
            <h2
              className="font-cinzel"
              style={{ fontSize: "1.2rem", fontWeight: 700, color: "var(--white-spectral)" }}
            >
              Contact
            </h2>
          </div>
          <button
            onClick={onClose}
            style={{ background: "transparent", border: "none", cursor: "pointer", color: "var(--gray-silver)", padding: 4 }}
          >
            <X size={16} />
          </button>
        </div>

        {/* Séparateur */}
        <div style={{ height: 1, background: "linear-gradient(90deg, var(--red-dark), transparent)", marginBottom: 24 }} />

        <form onSubmit={handleSubmit}>
          {/* Prénom / Nom */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
            <div>
              <label style={LABEL_STYLE}>Prénom *</label>
              <input
                required
                type="text"
                value={form.first_name}
                onChange={(e) => set("first_name", e.target.value)}
                style={FIELD_STYLE}
                placeholder="Alice"
              />
            </div>
            <div>
              <label style={LABEL_STYLE}>Nom *</label>
              <input
                required
                type="text"
                value={form.last_name}
                onChange={(e) => set("last_name", e.target.value)}
                style={FIELD_STYLE}
                placeholder="Dupont"
              />
            </div>
          </div>

          {/* Email */}
          <div style={{ marginBottom: 16 }}>
            <label style={LABEL_STYLE}>Email *</label>
            <input
              required
              type="email"
              value={form.email}
              onChange={(e) => set("email", e.target.value)}
              style={FIELD_STYLE}
              placeholder="alice@entreprise.com"
            />
          </div>

          {/* Téléphone / Poste */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
            <div>
              <label style={LABEL_STYLE}>Téléphone</label>
              <input
                type="tel"
                value={form.phone}
                onChange={(e) => set("phone", e.target.value)}
                style={FIELD_STYLE}
                placeholder="+33 6 …"
              />
            </div>
            <div>
              <label style={LABEL_STYLE}>Poste</label>
              <input
                type="text"
                value={form.job_title}
                onChange={(e) => set("job_title", e.target.value)}
                style={FIELD_STYLE}
                placeholder="Sales Manager"
              />
            </div>
          </div>

          {/* Statut */}
          <div style={{ marginBottom: 24 }}>
            <label style={LABEL_STYLE}>Statut</label>
            <select
              value={form.status}
              onChange={(e) => set("status", e.target.value as ContactStatus)}
              style={FIELD_STYLE}
            >
              {STATUS_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
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
              disabled={isPending}
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
              disabled={isPending}
              className="font-cinzel"
              style={{
                background: isPending ? "rgba(138,0,0,0.2)" : "rgba(138,0,0,0.35)",
                border: "1px solid var(--red-dark)",
                borderRadius: 4,
                padding: "8px 20px",
                color: isPending ? "var(--gray-silver)" : "var(--white-spectral)",
                cursor: isPending ? "not-allowed" : "pointer",
                fontSize: "0.7rem",
                letterSpacing: "0.1em",
                textTransform: "uppercase",
                boxShadow: isPending ? "none" : "var(--glow-red)",
                transition: "all 0.2s",
              }}
            >
              {isPending ? "Enregistrement…" : isEdit ? "Modifier" : "Créer"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
