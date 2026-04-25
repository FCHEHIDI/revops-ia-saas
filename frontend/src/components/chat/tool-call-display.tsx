"use client";
import { ToolInvocationCard } from "./ToolInvocationCard";
import type { ToolCallData } from "@/types";

interface ToolCallDisplayProps {
  toolCalls: ToolCallData[];
}

export function ToolCallDisplay({ toolCalls }: ToolCallDisplayProps) {
  if (toolCalls.length === 0) return null;
  return (
    <div className="mt-2 space-y-1.5">
      {toolCalls.map((tc, i) => (
        <ToolInvocationCard key={i} toolCall={tc} />
      ))}
    </div>
  );
}
