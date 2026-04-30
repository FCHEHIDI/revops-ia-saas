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

/** Brand accent colours */
export const C = {
  /** Analytics data / neutral positive  → --mcp-analytics  */
  blue:    "#50b4ff",
  /** Billing / paid / growth            → --mcp-billing    */
  green:   "#78ffa0",
  /** Sequences / secondary series       → --mcp-sequences  */
  purple:  "#c88cff",
  /** CRM / danger / overdue             → --mcp-crm        */
  red:     "#ff5050",
  /** Alerte modérée                     → --accent-warning */
  magenta: "#ff0066",
  /** Très positif (expansion)           → --accent-success */
  success: "#00ff88",
  /** Text-muted                         → --text-muted     */
  muted:   "#555555",
  /** Text-secondary                     → --text-secondary */
  secondary: "#999999",
  /** Text-primary                       → --text-primary   */
  primary: "#f5f5f5",
  /** Bg elevated                        → --bg-elevated    */
  elevated:"#1a1a1a",
  /** Border default                     → --border-default */
  border:  "#2a2a2a",
} as const;

/** Default Recharts element props */
export const CHART = {
  font:           "'Space Grotesk', system-ui, sans-serif",
  fontSize:       11,
  /** Axis tick colour */
  tick:           "#555555",
  /** Grid line colour */
  grid:           "rgba(255,255,255,0.05)",
  /** Recharts default chart margin */
  margin:         { top: 6, right: 8, left: 0, bottom: 0 } as const,
} as const;

/** Inline style for custom tooltip containers */
export const tooltipStyle: CSSProperties = {
  background:    "#1a1a1a",
  border:        "1px solid rgba(255,255,255,0.08)",
  borderRadius:  8,
  padding:       "8px 12px",
  fontSize:      12,
  fontFamily:    CHART.font,
  boxShadow:     "0 8px 32px rgba(0,0,0,0.8)",
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
  if (value >= goodThreshold) return C.green;
  if (value >= warnThreshold) return C.blue;
  return C.magenta;
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
