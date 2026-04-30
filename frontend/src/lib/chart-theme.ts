import type { CSSProperties } from "react";

/**
 * Recharts colour palette aligned with the RevOps brand (globals.css).
 *
 * Usage:
 *   import { C, CHART, tooltipStyle } from "@/lib/chart-theme";
 *
 *   <Area stroke={C.blue} fill={C.blue} ... />
 *   <XAxis tick={{ fill: CHART.tick, fontSize: CHART.fontSize }} ... />
 *   function CustomTooltip(...) {
 *     return <div style={tooltipStyle}>...</div>;
 *   }
 */

/** Brand accent colours — venetian gothic palette */
export const C = {
  /** Ambre vénitien (alerte modérée / neutral)   */
  blue:    "#C07000",
  /** Or vénitien sombre (croissance / positif)   */
  green:   "#A07800",
  /** Améthyste profonde (séquences)              */
  purple:  "#6B2080",
  /** Rouge incandescent (danger / retard)        */
  red:     "#FF1A1A",
  /** Magenta alerte (goulot / warning)           */
  magenta: "#FF0066",
  /** Or vif (expansion / très positif)           */
  success: "#D4A000",
  /** Muted vénitien sombre                       */
  muted:   "#5A3535",
  /** Secondaire vénitien                         */
  secondary: "#9A6B6B",
  /** Blanc spectral (texte primaire)             */
  primary: "#F2F2F2",
  /** Noir marbre (bg élevé)                      */
  elevated:"#0A0A0A",
  /** Bordure vénitienne sombre                   */
  border:  "#3D1A1A",
} as const;

/** Default Recharts element props */
export const CHART = {
  font:           "'Space Grotesk', system-ui, sans-serif",
  fontSize:       11,
  /** Axis tick colour — venetian dark red */
  tick:           "#7A4040",
  /** Grid line colour — red holographic */
  grid:           "rgba(192,0,0,0.12)",
  /** Recharts default chart margin */
  margin:         { top: 6, right: 8, left: 0, bottom: 0 } as const,
} as const;

/** Inline style for custom tooltip containers */
export const tooltipStyle: CSSProperties = {
  background:    "rgba(5,5,5,0.95)",
  border:        "1px solid rgba(192,0,0,0.45)",
  borderRadius:  6,
  padding:       "8px 12px",
  fontSize:      12,
  fontFamily:    CHART.font,
  boxShadow:     "0 8px 32px rgba(0,0,0,0.9), 0 0 16px rgba(192,0,0,0.2)",
  color:         C.primary,
};

/**
 * Returns a colour representing the health of a conversion/rate metric.
 *   >= goodThreshold → green
 *   >= warnThreshold → blue
 *   default          → magenta (alerte)
 */
export function healthColor(
  value: number,
  goodThreshold: number,
  warnThreshold: number
): string {
  if (value >= goodThreshold) return "#D4A000"; // or vénitien — bon
  if (value >= warnThreshold) return "#C00000"; // rouge vénitien — modéré
  return "#FF1A1A";                             // rouge incandescent — critique
}

/** Format a euro amount: 28400 → "28k€", 900 → "900€" */
export function fmtEur(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M€`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(0)}k€`;
  return `${value}€`;
}

/** French month short names indexed 0–11 */
const FR_MONTHS = ["Jan","Fév","Mar","Avr","Mai","Jun","Jul","Aoû","Sep","Oct","Nov","Déc"] as const;

/** "2026-04-01" → "Avr" */
export function fmtMonth(isoDate: string): string {
  const parts = isoDate.split("-");
  const monthIndex = parseInt(parts[1] ?? "1", 10) - 1;
  return FR_MONTHS[monthIndex] ?? isoDate;
}
