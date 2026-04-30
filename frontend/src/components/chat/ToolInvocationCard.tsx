"use client";
import { useState } from "react";
import { ChevronDown, ChevronRight, Database, BarChart2, Receipt, GitBranch, Wrench } from "lucide-react";
import type { ToolCallData } from "@/types";

/** Pick an icon and accent colour based on the MCP service prefix */
function toolMeta(tool: string): { icon: React.ReactNode; accent: string; label: string } {
  if (tool.startsWith("mcp_crm"))
    return { icon: <Database size={11} />, accent: "rgba(255,80,80,0.8)", label: "CRM" };
  if (tool.startsWith("mcp_analytics"))
    return { icon: <BarChart2 size={11} />, accent: "rgba(80,180,255,0.8)", label: "Analytics" };
  if (tool.startsWith("mcp_billing"))
    return { icon: <Receipt size={11} />, accent: "rgba(120,255,160,0.8)", label: "Billing" };
  if (tool.startsWith("mcp_sequences"))
    return { icon: <GitBranch size={11} />, accent: "rgba(200,140,255,0.8)", label: "Sequences" };
  return { icon: <Wrench size={11} />, accent: "rgba(200,200,200,0.7)", label: "Tool" };
}

/** Syntax-highlight a JSON string with <span> colours */
function JsonHighlight({ value }: { value: unknown }) {
  const raw = JSON.stringify(value, null, 2);
  const highlighted = raw
    .replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?)/g, (match) =>
      match.endsWith(":")
        ? `<span style="color:#f87171">${match}</span>`   // key — red
        : `<span style="color:#86efac">${match}</span>`,  // string value — green
    )
    .replace(/\b(true|false)\b/g, `<span style="color:#67e8f9">$1</span>`)  // bool — cyan
    .replace(/\b(null)\b/g, `<span style="color:#94a3b8">$1</span>`)         // null — slate
    .replace(/\b(\d+\.?\d*)\b/g, `<span style="color:#fbbf24">$1</span>`);  // number — amber

  return (
    <pre
      className="font-mono-geist text-xs overflow-auto max-h-56 whitespace-pre-wrap break-all leading-5"
      style={{ color: "#94a3b8" }}
      dangerouslySetInnerHTML={{ __html: highlighted }}
    />
  );
}

export function ToolInvocationCard({ toolCall }: { toolCall: ToolCallData }) {
  const [expanded, setExpanded] = useState(false);
  const { icon, accent, label } = toolMeta(toolCall.tool);

  // Derive a readable function name from the full tool string
  const parts = toolCall.tool.split("__");
  const fnName = parts.length > 1 ? parts.slice(1).join("__") : toolCall.tool;

  return (
    <div
      className="rounded-lg overflow-hidden transition-all duration-200"
      style={{
        border: `1px solid ${accent.replace("0.8", "0.2")}`,
        background: `${accent.replace("0.8", "0.04")}`,
      }}
    >
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors duration-150"
        style={{ color: accent }}
        onMouseEnter={(e) => { e.currentTarget.style.background = accent.replace("0.8", "0.07"); }}
        onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
        aria-expanded={expanded}
        aria-controls={`tool-result-${toolCall.tool}`}
      >
        {/* Service icon */}
        <span className="shrink-0" style={{ color: accent }}>{icon}</span>

        {/* Service badge */}
        <span
          className="font-mono-geist shrink-0 rounded px-1 py-0.5"
          style={{
            fontSize: "9px",
            letterSpacing: "0.1em",
            color: accent,
            background: accent.replace("0.8", "0.1"),
            border: `1px solid ${accent.replace("0.8", "0.2")}`,
          }}
        >
          {label}
        </span>

        {/* Function name */}
        <span
          className="font-mono-geist font-medium truncate"
          style={{ fontSize: "11px", letterSpacing: "0.04em", color: accent.replace("0.8", "0.9") }}
        >
          {fnName}
        </span>

        {/* Result count badge */}
        {toolCall.result && typeof toolCall.result === "object" && "total" in (toolCall.result as object) && (
          <span
            className="font-mono-geist ml-1 shrink-0 rounded-full px-1.5 py-0.5"
            style={{
              fontSize: "9px",
              color: accent.replace("0.8", "0.7"),
              background: accent.replace("0.8", "0.1"),
            }}
          >
            {(toolCall.result as { total: number }).total} résultats
          </span>
        )}

        <span className="ml-auto shrink-0 opacity-40" style={{ color: accent }}>
          {expanded ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
        </span>
      </button>

      {/* Collapsible JSON panel */}
      <div
        id={`tool-result-${toolCall.tool}`}
        className="overflow-hidden transition-all duration-200"
        style={{
          maxHeight: expanded ? "300px" : "0px",
          borderTop: expanded ? `1px solid ${accent.replace("0.8", "0.12")}` : "none",
        }}
      >
        <div className="px-3 py-2.5" style={{ background: "rgba(0,0,0,0.25)" }}>
          <JsonHighlight value={toolCall.result} />
        </div>
      </div>
    </div>
  );
}
