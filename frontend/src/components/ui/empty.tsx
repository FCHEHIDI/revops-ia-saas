import { type ReactNode } from "react";

interface EmptyStateProps {
  /** Glyph ou emoji affiché en grand — ex: "⚜", "📭", "🗂" */
  icon?: string;
  /** Titre principal */
  title: string;
  /** Description optionnelle sous le titre */
  description?: string;
  /** Bouton d'action principal */
  action?: {
    label: string;
    onClick: () => void;
    icon?: ReactNode;
  };
  /** Contenu custom à la place du bouton (lien, multi-actions…) */
  children?: ReactNode;
}

export function EmptyState({ icon = "⚜", title, description, action, children }: EmptyStateProps) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "64px 32px",
        textAlign: "center",
      }}
    >
      {/* Icon */}
      <span
        style={{
          fontSize: 40,
          lineHeight: 1,
          marginBottom: 20,
          opacity: 0.35,
          filter: "drop-shadow(0 0 8px rgba(192,0,0,0.3))",
          display: "block",
        }}
      >
        {icon}
      </span>

      {/* Title */}
      <p
        style={{
          fontSize: 15,
          fontWeight: 600,
          color: "var(--text-primary)",
          fontFamily: "var(--font-body)",
          marginBottom: description ? 8 : action || children ? 20 : 0,
          lineHeight: 1.4,
        }}
      >
        {title}
      </p>

      {/* Description */}
      {description && (
        <p
          style={{
            fontSize: 13,
            color: "var(--text-secondary)",
            fontFamily: "var(--font-body)",
            marginBottom: action || children ? 24 : 0,
            maxWidth: 320,
            lineHeight: 1.6,
          }}
        >
          {description}
        </p>
      )}

      {/* CTA button */}
      {action && !children && (
        <button
          onClick={action.onClick}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            padding: "9px 18px",
            background: "var(--red-doge)",
            color: "#fff",
            border: "none",
            borderRadius: "var(--radius-btn)",
            fontSize: 13,
            fontWeight: 600,
            fontFamily: "var(--font-body)",
            cursor: "pointer",
            transition: "background 0.15s, box-shadow 0.15s",
            boxShadow: "0 0 16px rgba(192,0,0,0.25)",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = "#A00000";
            e.currentTarget.style.boxShadow = "0 0 24px rgba(192,0,0,0.4)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = "var(--red-doge)";
            e.currentTarget.style.boxShadow = "0 0 16px rgba(192,0,0,0.25)";
          }}
        >
          {action.icon}
          {action.label}
        </button>
      )}

      {/* Custom children */}
      {children}
    </div>
  );
}
