"use client";
import { useState } from "react";
import { ChevronDown, ChevronRight, Database, BarChart2, Receipt, GitBranch, Wrench } from "lucide-react";
import type { ToolCallData } from "@/types";

/** CSS-var-based palette per MCP service */
type ServiceMeta = { icon: React.ReactNode; color: string; border: string; bg: string; bgHover: string; label: string };

function toolMeta(tool: string): ServiceMeta {
  if (tool.startsWith("mcp_crm"))
    return { icon: <Database size={11} />, color: "var(--mcp-crm)", border: "var(--mcp-crm-border)", bg: "var(--mcp-crm-bg)", bgHover: "rgba(255,80,80,0.07)", label: "CRM" };
  if (tool.startsWith("mcp_analytics"))
    return { icon: <BarChart2 size={11} />, color: "var(--mcp-analytics)", border: "var(--mcp-analytics-border)", bg: "var(--mcp-analytics-bg)", bgHover: "rgba(80,180,255,0.07)", label: "Analytics" };
  if (tool.startsWith("mcp_billing"))
    return { icon: <Receipt size={11} />, color: "var(--mcp-billing)", border: "var(--mcp-billing-border)", bg: "var(--mcp-billing-bg)", bgHover: "rgba(120,255,160,0.07)", label: "Billing" };
  if (tool.startsWith("mcp_sequences"))
    return { icon: <GitBranch size={11} />, color: "var(--mcp-sequences)", border: "var(--mcp-sequences-border)", bg: "var(--mcp-sequences-bg)", bgHover: "rgba(200,140,255,0.07)", label: "Sequences" };
  return { icon: <Wrench size={11} />, color: "var(--mcp-default)", border: "var(--mcp-default-border)", bg: "var(--mcp-default-bg)", bgHover: "rgba(200,200,200,0.07)", label: "Tool" };
}

/** Syntax-highlight a JSON string with <span> colours */
function JsonHighlight({ value }: { value: unknown }) {
  const raw = JSON.stringify(value, null, 2);
  const highlighted = raw
    .replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?)/g, (match) =>
      match.endsWith(":")
        ? `<span style="color:#f87171">${match}</span>`
        : `<span style="color:#86efac">${match}</span>`,
    )
    .replace(/\b(true|false)\b/g, `<span style="color:#67e8f9">$1</span>`)
    .replace(/\b(null)\b/g, `<span style="color:#94a3b8">$1</span>`)
    .replace(/\b(\d+\.?\d*)\b/g, `<span style="color:#fbbf24">$1</span>`);

  return (
    <pre
      className="font-mono-geist text-xs overflow-auto max-h-56 whitespace-pre-wrap break-all leading-5"
      style={{ color: "#94a3b8" }}
      dangerouslySetInnerHTML={{ __html: highlighted }}
    />
  );
}

/** Returns true if the tool result indicates an error/failure */
function isToolError(result: unknown): boolean {
  if (result == null) return false;
  if (typeof result === "string") {
    const lower = result.toLowerCase();
    return lower.includes("error") || lower.includes("failed") || lower.includes("unavailable");
  }
  if (typeof result === "object") {
    const r = result as Record<string, unknown>;
    return "error" in r || "message" in r && typeof r.message === "string" && r.message.toLowerCase().includes("error");
  }
  return false;
}

export function ToolInvocationCard({ toolCall }: { toolCall: ToolCallData }) {
  const [expanded, setExpanded] = useState(false);
  const { icon, color, border, bg, bgHover, label } = toolMeta(toolCall.tool);

  const parts = toolCall.tool.split("__");
  const fnName = parts.length > 1 ? parts.slice(1).join("__") : toolCall.tool;

  const resultTotal =
    toolCall.result &&
    typeof toolCall.result === "object" &&
    "total" in (toolCall.result as object)
      ? (toolCall.result as { total: number }).total
      : null;

  const hasError = isToolError(toolCall.result);
  const statusColor = hasError ? "#ff4444" : "#4dff91";
  const statusLabel = hasError ? "FAILED" : "OK";

  const cardBorder = hasError ? "rgba(255,68,68,0.35)"  : border;
  const cardBg     = hasError ? "rgba(255,68,68,0.06)"  : bg;
  const cardHover  = hasError ? "rgba(255,68,68,0.10)"  : bgHover;
  const cardColor  = hasError ? "rgba(255,120,120,0.9)" : color;

  return (
    <div
      className="rounded-lg overflow-hidden transition-all duration-200"
      style={{ border: `1px solid ${cardBorder}`, background: cardBg }}
    >
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors duration-150"
        style={{ color: cardColor }}
        onMouseEnter={(e) => { e.currentTarget.style.background = cardHover; }}
        onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
        aria-expanded={expanded}
        aria-controls={`tool-result-${toolCall.tool}`}
      >
        <span className="shrink-0">{icon}</span>

        <span
          className="font-mono-geist shrink-0 rounded px-1 py-0.5"
          style={{
            fontSize: "9px",
            letterSpacing: "0.1em",
            color: cardColor,
            background: "var(--chat-tool-json-bg)",
            border: `1px solid ${cardBorder}`,
          }}
        >
          {label}
        </span>

        <span
          className="font-mono-geist font-medium truncate"
          style={{ fontSize: "11px", letterSpacing: "0.04em", color: cardColor }}
        >
          {fnName}
        </span>

        {resultTotal !== null && (
          <span
            className="font-mono-geist ml-1 shrink-0 rounded-full px-1.5 py-0.5"
            style={{ fontSize: "9px", color: cardColor, background: "var(--chat-tool-json-bg)" }}
          >
            {resultTotal} résultats
          </span>
        )}

        {/* Status dot — vert = OK, rouge = FAILED */}
        <span
          className="font-mono-geist ml-auto shrink-0 flex items-center gap-1"
          style={{ fontSize: "8px", color: statusColor, letterSpacing: "0.08em" }}
        >
          <span
            style={{
              display: "inline-block",
              width: 5,
              height: 5,
              borderRadius: "50%",
              background: statusColor,
              boxShadow: `0 0 4px ${statusColor}`,
              flexShrink: 0,
            }}
          />
          {statusLabel}
        </span>

        <span className="ml-2 shrink-0 opacity-40">
          {expanded ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
        </span>
      </button>

      <div
        id={`tool-result-${toolCall.tool}`}
        className="overflow-hidden transition-all duration-200"
        style={{
          maxHeight: expanded ? "300px" : "0px",
          borderTop: expanded ? `1px solid ${cardBorder}` : "none",
        }}
      >
        <div className="px-3 py-2.5" style={{ background: "var(--chat-tool-json-bg)" }}>
          <JsonHighlight value={toolCall.result} />
        </div>
      </div>
    </div>
  );
}
