"use client";

import { useRef, useState, type DragEvent, type ChangeEvent } from "react";
import { Trash2, CheckCircle, AlertCircle, Loader } from "lucide-react";
import { Spinner } from "@/components/ui/spinner";
import { useApiQuery, useApiMutation } from "@/hooks/useApi";
import { documentsApi } from "@/lib/api";
import { formatBytes, formatDate } from "@/lib/utils";
import type { Document, DocumentStatus } from "@/types";

// ── Palette Salle des Manuscrits ──────────────────────────────────────────────
const STATUS_CFG: Record<
  DocumentStatus,
  { label: string; color: string; bg: string; border: string; glyph: string; Icon: React.ElementType }
> = {
  indexed: {
    label: "Indexé",
    color: "#D4A000",
    bg: "rgba(212,160,0,0.12)",
    border: "rgba(212,160,0,0.35)",
    glyph: "✦",
    Icon: CheckCircle,
  },
  processing: {
    label: "En cours",
    color: "#C07000",
    bg: "rgba(192,112,0,0.12)",
    border: "rgba(192,112,0,0.35)",
    glyph: "◌",
    Icon: Loader,
  },
  uploading: {
    label: "Upload…",
    color: "#7A6040",
    bg: "rgba(122,96,64,0.10)",
    border: "rgba(122,96,64,0.30)",
    glyph: "◎",
    Icon: Loader,
  },
  error: {
    label: "Erreur",
    color: "#FF1A1A",
    bg: "rgba(255,26,26,0.12)",
    border: "rgba(255,26,26,0.40)",
    glyph: "⚠",
    Icon: AlertCircle,
  },
};

// ── StatusBadge ───────────────────────────────────────────────────────────────
function StatusBadge({ status }: { status: DocumentStatus }) {
  const cfg = STATUS_CFG[status];
  return (
    <span
      className="font-cinzel tracking-[0.10em] uppercase"
      style={{
        fontSize: 10,
        color: cfg.color,
        background: cfg.bg,
        border: `1px solid ${cfg.border}`,
        borderRadius: 4,
        padding: "2px 8px",
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        whiteSpace: "nowrap",
      }}
    >
      <span>{cfg.glyph}</span>
      {cfg.label}
    </span>
  );
}

// ── DocumentsUpload ───────────────────────────────────────────────────────────
export function DocumentsUpload() {
  const [isDragging, setIsDragging] = useState(false);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { data: documents, isLoading } = useApiQuery(["documents"], () =>
    documentsApi.listDocuments()
  );

  const uploadMutation = useApiMutation(
    (file: File) => documentsApi.uploadDocument(file),
    [["documents"]]
  );

  const deleteMutation = useApiMutation(
    (id: string) => documentsApi.deleteDocument(id),
    [["documents"]]
  );

  const handleFiles = (files: FileList | null) => {
    if (!files) return;
    Array.from(files).forEach((file) => uploadMutation.mutate(file));
  };

  const handleDrop = (e: DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    handleFiles(e.dataTransfer.files);
  };

  const handleDragOver = (e: DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const docList: Document[] = documents ?? [];
  const indexedCount = docList.filter((d) => d.status === "indexed").length;
  const processingCount = docList.filter(
    (d) => d.status === "processing" || d.status === "uploading"
  ).length;
  const errorCount = docList.filter((d) => d.status === "error").length;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>
      {/* ── Zone de dépôt ── */}
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={() => setIsDragging(false)}
        onClick={() => fileInputRef.current?.click()}
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 16,
          borderRadius: 8,
          border: `2px dashed ${isDragging ? "rgba(212,160,0,0.70)" : "rgba(192,112,0,0.35)"}`,
          padding: "40px 24px",
          cursor: "pointer",
          background: isDragging
            ? "rgba(138,88,0,0.10)"
            : "rgba(10,10,10,0.70)",
          backdropFilter: "blur(6px)",
          transition: "border-color 0.2s, background 0.2s",
          boxShadow: isDragging
            ? "0 0 30px rgba(212,160,0,0.15) inset"
            : "none",
        }}
      >
        {/* Glyphe parchemin */}
        <div
          style={{
            width: 52,
            height: 52,
            borderRadius: 8,
            background: "rgba(192,112,0,0.12)",
            border: "1px solid rgba(192,112,0,0.35)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 24,
            color: isDragging ? "#D4A000" : "#C07000",
            textShadow: isDragging ? "0 0 18px rgba(212,160,0,0.6)" : "none",
          }}
        >
          📜
        </div>
        <div style={{ textAlign: "center" }}>
          <p
            className="font-cinzel"
            style={{ fontSize: 13, color: "var(--white-spectral)", marginBottom: 4 }}
          >
            Déposer un manuscrit ou{" "}
            <span style={{ color: "#D4A000", textDecoration: "underline" }}>
              parcourir
            </span>
          </p>
          <p
            style={{
              fontSize: 11,
              color: "var(--gray-silver)",
              fontFamily: "var(--font-body)",
              letterSpacing: "0.08em",
            }}
          >
            PDF · DOCX · TXT · MD — max 50 MB
          </p>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,.docx,.txt,.md"
          style={{ display: "none" }}
          onChange={(e: ChangeEvent<HTMLInputElement>) => handleFiles(e.target.files)}
        />
      </div>

      {/* ── Upload en cours ── */}
      {uploadMutation.isPending && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            fontSize: 13,
            color: "#C07000",
            fontFamily: "var(--font-body)",
          }}
        >
          <Spinner size="sm" />
          Inscription au registre en cours…
        </div>
      )}

      {/* ── KPIs ── */}
      {docList.length > 0 && (
        <div style={{ display: "flex", gap: 12 }}>
          {/* Indexés */}
          <div
            style={{
              flex: 1,
              background: "rgba(212,160,0,0.08)",
              border: "1px solid rgba(212,160,0,0.25)",
              borderRadius: 8,
              padding: "14px 18px",
            }}
          >
            <div
              style={{ fontSize: 11, color: "#C07000", letterSpacing: "0.12em", marginBottom: 4 }}
              className="font-cinzel uppercase tracking-widest"
            >
              ✦ Indexés
            </div>
            <div
              style={{ fontSize: 22, color: "#D4A000", fontFamily: "var(--font-mono)", fontWeight: 700 }}
            >
              {indexedCount}
            </div>
          </div>
          {/* En traitement */}
          <div
            style={{
              flex: 1,
              background: "rgba(192,112,0,0.07)",
              border: "1px solid rgba(192,112,0,0.22)",
              borderRadius: 8,
              padding: "14px 18px",
            }}
          >
            <div
              style={{ fontSize: 11, color: "#7A6040", letterSpacing: "0.12em", marginBottom: 4 }}
              className="font-cinzel uppercase tracking-widest"
            >
              ◌ Traitement
            </div>
            <div
              style={{ fontSize: 22, color: "#C07000", fontFamily: "var(--font-mono)", fontWeight: 700 }}
            >
              {processingCount}
            </div>
          </div>
          {/* Erreurs */}
          <div
            style={{
              flex: 1,
              background: "rgba(255,26,26,0.07)",
              border: "1px solid rgba(255,26,26,0.22)",
              borderRadius: 8,
              padding: "14px 18px",
            }}
          >
            <div
              style={{ fontSize: 11, color: "#8A0000", letterSpacing: "0.12em", marginBottom: 4 }}
              className="font-cinzel uppercase tracking-widest"
            >
              ⚠ Erreurs
            </div>
            <div
              style={{ fontSize: 22, color: "#FF1A1A", fontFamily: "var(--font-mono)", fontWeight: 700 }}
            >
              {errorCount}
            </div>
          </div>
        </div>
      )}

      {/* ── Séparateur ── */}
      <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
        <div style={{ flex: 1, height: 1, background: "rgba(138,0,0,0.35)" }} />
        <span
          className="font-cinzel"
          style={{ fontSize: 11, color: "#C07000", letterSpacing: "0.22em", whiteSpace: "nowrap" }}
        >
          ◈ Registre des Manuscrits
        </span>
        <div style={{ flex: 1, height: 1, background: "rgba(138,0,0,0.35)" }} />
      </div>

      {/* ── Liste des documents ── */}
      {isLoading ? (
        <div style={{ display: "flex", justifyContent: "center", padding: "40px 0" }}>
          <Spinner size="lg" />
        </div>
      ) : docList.length === 0 ? (
        <div
          style={{
            padding: "48px 24px",
            textAlign: "center",
            color: "var(--gray-silver)",
            fontFamily: "var(--font-body)",
            fontSize: 13,
          }}
        >
          <div style={{ fontSize: 28, marginBottom: 12, opacity: 0.4 }}>📜</div>
          <p className="font-cinzel" style={{ color: "#7A5535", fontSize: 12, letterSpacing: "0.15em" }}>
            Nulla manuscripta — aucun document inscrit
          </p>
          <p style={{ marginTop: 6, fontSize: 11 }}>
            Déposez vos premiers fichiers ci-dessus pour les indexer.
          </p>
        </div>
      ) : (
        <div
          className="tablette-marbre"
          style={{
            borderRadius: 8,
            overflow: "hidden",
            border: "1px solid rgba(138,0,0,0.30)",
          }}
        >
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr
                style={{
                  background: "rgba(34,0,0,0.60)",
                  borderBottom: "1px solid rgba(138,0,0,0.40)",
                }}
              >
                {["Manuscrit", "Taille", "Indexé le", "Fragments", "État", ""].map((h) => (
                  <th
                    key={h}
                    className="font-cinzel"
                    style={{
                      padding: "10px 14px",
                      textAlign: "left",
                      fontSize: 10,
                      color: "#C07000",
                      letterSpacing: "0.18em",
                      fontWeight: 600,
                      textTransform: "uppercase",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {docList.map((doc: Document) => {
                const isHovered = hoveredId === doc.id;
                return (
                  <tr
                    key={doc.id}
                    onMouseEnter={() => setHoveredId(doc.id)}
                    onMouseLeave={() => setHoveredId(null)}
                    style={{
                      borderBottom: "1px solid rgba(138,0,0,0.18)",
                      background: isHovered
                        ? "rgba(138,88,0,0.07)"
                        : "transparent",
                      transition: "background 0.15s",
                    }}
                  >
                    {/* Nom */}
                    <td style={{ padding: "12px 14px", maxWidth: 260 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <span style={{ fontSize: 16, opacity: 0.7 }}>📄</span>
                        <span
                          style={{
                            fontSize: 13,
                            color: "var(--white-spectral)",
                            fontFamily: "var(--font-body)",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                          }}
                        >
                          {doc.filename}
                        </span>
                      </div>
                    </td>
                    {/* Taille */}
                    <td style={{ padding: "12px 14px", whiteSpace: "nowrap" }}>
                      <span
                        style={{
                          fontSize: 12,
                          color: "var(--gray-silver)",
                          fontFamily: "var(--font-mono)",
                        }}
                      >
                        {formatBytes(doc.size)}
                      </span>
                    </td>
                    {/* Date */}
                    <td style={{ padding: "12px 14px", whiteSpace: "nowrap" }}>
                      <span
                        style={{
                          fontSize: 12,
                          color: "var(--gray-silver)",
                          fontFamily: "var(--font-body)",
                        }}
                      >
                        {formatDate(doc.uploaded_at)}
                      </span>
                    </td>
                    {/* Chunks */}
                    <td style={{ padding: "12px 14px" }}>
                      <span
                        style={{
                          fontSize: 12,
                          color: doc.chunk_count ? "#D4A000" : "var(--gray-silver)",
                          fontFamily: "var(--font-mono)",
                        }}
                      >
                        {doc.chunk_count ?? "—"}
                      </span>
                    </td>
                    {/* Statut */}
                    <td style={{ padding: "12px 14px" }}>
                      <StatusBadge status={doc.status} />
                    </td>
                    {/* Action */}
                    <td style={{ padding: "12px 14px", textAlign: "right" }}>
                      <button
                        onClick={() => deleteMutation.mutate(doc.id)}
                        disabled={deleteMutation.isPending}
                        style={{
                          background: "transparent",
                          border: "none",
                          cursor: "pointer",
                          padding: "4px 8px",
                          borderRadius: 4,
                          color: isHovered ? "#FF1A1A" : "rgba(138,0,0,0.50)",
                          transition: "color 0.15s",
                          display: "flex",
                          alignItems: "center",
                        }}
                        title="Supprimer"
                      >
                        <Trash2 size={14} />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
