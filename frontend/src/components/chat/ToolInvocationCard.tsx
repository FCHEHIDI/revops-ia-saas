"use client";
import { useState } from "react";
import { ChevronDown, ChevronRight, Wrench } from "lucide-react";
import type { ToolCallData } from "@/types";

export function ToolInvocationCard({ toolCall }: { toolCall: ToolCallData }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div
      className="rounded-lg overflow-hidden"
      style={{ border: "1px solid rgba(255,0,0,0.15)", background: "rgba(255,0,0,0.04)" }}
    >
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs transition-colors"
        style={{ color: "rgba(255,80,80,0.8)" }}
        onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(255,0,0,0.06)"; }}
        onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
        aria-expanded={expanded}
        aria-controls={`tool-invocation-${toolCall.tool}`}
      >
        <Wrench size={11} className="shrink-0" style={{ color: "rgba(255,80,80,0.7)" }} />
        <span className="font-mono-geist font-medium" style={{ letterSpacing: "0.06em" }}>
          {toolCall.tool}
        </span>
        <span className="ml-auto opacity-50">
          {expanded ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
        </span>
      </button>
      {expanded && (
        <div
          id={`tool-invocation-${toolCall.tool}`}
          className="px-3 py-2"
          style={{ borderTop: "1px solid rgba(255,0,0,0.1)" }}
        >
          <pre className="font-mono-geist text-xs overflow-auto max-h-48 whitespace-pre-wrap break-all" style={{ color: "#555" }}>
            {JSON.stringify(toolCall.result, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
