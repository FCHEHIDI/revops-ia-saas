"use client";
import { useState } from "react";
import { ChevronDown, ChevronRight, Wrench } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ToolCallData } from "@/types";

export function ToolInvocationCard({ toolCall }: { toolCall: ToolCallData }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="rounded-lg border border-indigo-800/50 bg-indigo-950/30">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-indigo-300 hover:bg-indigo-900/20 transition-colors rounded-lg"
        aria-expanded={expanded}
        aria-controls={`tool-invocation-${toolCall.tool}`}
      >
        <Wrench size={12} className="shrink-0 text-indigo-400" />
        <span className="font-medium font-mono">{toolCall.tool}</span>
        <span className="ml-auto">
          {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        </span>
      </button>
      {expanded && (
        <div id={`tool-invocation-${toolCall.tool}`} className="border-t border-indigo-800/30 px-3 py-2">
          <pre
            className={cn(
              "text-xs text-slate-400 overflow-auto max-h-48 font-mono whitespace-pre-wrap break-all"
            )}
          >
            {JSON.stringify(toolCall.result, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
