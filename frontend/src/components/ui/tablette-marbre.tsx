"use client";

import { type ReactNode } from "react";
import { cn } from "@/lib/utils";

// ─────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────

type TabletteVariant = "default" | "metrique" | "graphique" | "narrative" | "interactive";

interface TabletteMarbreProps {
  /** Variante visuelle de la tablette */
  variant?: TabletteVariant;
  /** Active le pulse Marbre continu (pour alertes, focus) */
  active?: boolean;
  /** Classes CSS supplémentaires */
  className?: string;
  /** Handler click (active automatiquement la variante interactive) */
  onClick?: () => void;
  children: ReactNode;
}

// ─────────────────────────────────────────────────────────────
// Composant racine
// ─────────────────────────────────────────────────────────────

export function TabletteMarbre({
  variant = "default",
  active = false,
  className,
  onClick,
  children,
}: TabletteMarbreProps) {
  const isInteractive = variant === "interactive" || !!onClick;

  return (
    <div
      onClick={onClick}
      className={cn(
        "tablette-marbre",
        variant !== "default" && `tablette-${variant}`,
        active && "active",
        isInteractive && "tablette-interactive",
        className,
      )}
    >
      {children}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Sub-composants utilitaires
// ─────────────────────────────────────────────────────────────

/** En-tête avec médaillon icône + titre + sous-titre */
export function TabletteHeader({
  icon,
  title,
  subtitle,
}: {
  icon?: ReactNode;
  title: string;
  subtitle?: string;
}) {
  return (
    <div className="tm-header">
      {icon && <div className="tm-icon">{icon}</div>}
      <div>
        <div className="tm-heading">{title}</div>
        {subtitle && <div className="tm-subheading">{subtitle}</div>}
      </div>
    </div>
  );
}

/** Séparateur horizontal veinure rouge */
export function TabletteDivider() {
  return <div className="tm-divider" />;
}

/** Badge d'état : "default" = rouge, "success" = vert, "warning" = ambre */
export function TabletteBadge({
  children,
  status = "default",
}: {
  children: ReactNode;
  status?: "default" | "success" | "warning";
}) {
  return (
    <span className={cn("tm-badge", status !== "default" && status)}>
      {children}
    </span>
  );
}

// ─────────────────────────────────────────────────────────────
// Variante Métrique — gros chiffre + label + delta
// ─────────────────────────────────────────────────────────────

interface MetriqueProps {
  /** La valeur principale affichée en grand */
  value: string | number;
  /** Label sous la valeur */
  label: string;
  /** Variation (ex: "+12.4%", "−3") */
  delta?: string;
  /** Sens de la variation */
  trend?: "positive" | "negative" | "neutral";
  icon?: ReactNode;
  title?: string;
  className?: string;
  active?: boolean;
}

export function TabletteMetrique({
  value,
  label,
  delta,
  trend = "neutral",
  icon,
  title,
  className,
  active = false,
}: MetriqueProps) {
  return (
    <TabletteMarbre variant="metrique" active={active} className={className}>
      {(icon || title) && (
        <TabletteHeader icon={icon} title={title ?? ""} />
      )}
      <div className="tm-value">{value}</div>
      <div className="tm-label">{label}</div>
      {delta && (
        <div className={cn("tm-delta", trend !== "neutral" && trend)}>
          {delta}
        </div>
      )}
    </TabletteMarbre>
  );
}

// ─────────────────────────────────────────────────────────────
// Variante Graphique — titre + zone de chart injectée
// ─────────────────────────────────────────────────────────────

interface GraphiqueProps {
  title: string;
  subtitle?: string;
  icon?: ReactNode;
  children: ReactNode;
  className?: string;
  active?: boolean;
}

export function TabletteGraphique({
  title,
  subtitle,
  icon,
  children,
  className,
  active = false,
}: GraphiqueProps) {
  return (
    <TabletteMarbre variant="graphique" active={active} className={className}>
      <TabletteHeader icon={icon} title={title} subtitle={subtitle} />
      <div className="tm-chart-zone">{children}</div>
    </TabletteMarbre>
  );
}

// ─────────────────────────────────────────────────────────────
// Variante Narrative — glyphe + citation / texte
// ─────────────────────────────────────────────────────────────

interface NarrativeProps {
  glyph?: string;
  quote?: string;
  children?: ReactNode;
  className?: string;
}

export function TabletteNarrative({
  glyph,
  quote,
  children,
  className,
}: NarrativeProps) {
  return (
    <TabletteMarbre variant="narrative" className={className}>
      {glyph && <div className="tm-glyph">{glyph}</div>}
      {quote && <blockquote className="tm-quote">{quote}</blockquote>}
      {children}
    </TabletteMarbre>
  );
}

// ─────────────────────────────────────────────────────────────
// Variante Interactive — click + hover intense
// ─────────────────────────────────────────────────────────────

interface InteractiveProps {
  icon?: ReactNode;
  title: string;
  subtitle?: string;
  badge?: ReactNode;
  onClick: () => void;
  children?: ReactNode;
  className?: string;
  active?: boolean;
}

export function TabletteInteractive({
  icon,
  title,
  subtitle,
  badge,
  onClick,
  children,
  className,
  active = false,
}: InteractiveProps) {
  return (
    <TabletteMarbre
      variant="interactive"
      active={active}
      onClick={onClick}
      className={className}
    >
      <div className="flex items-start justify-between gap-2">
        <TabletteHeader icon={icon} title={title} subtitle={subtitle} />
        {badge && <div className="shrink-0 pt-1">{badge}</div>}
      </div>
      {children && (
        <>
          <TabletteDivider />
          {children}
        </>
      )}
    </TabletteMarbre>
  );
}
