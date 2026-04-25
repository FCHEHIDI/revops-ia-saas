import { User, Bot } from "lucide-react";
import { cn } from "@/lib/utils";
import { ToolCallDisplay } from "./tool-call-display";
import type { ChatMessage } from "@/types";

interface MessageBubbleProps {
  message: ChatMessage;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div
      className={cn(
        "flex gap-3 max-w-full",
        isUser ? "flex-row-reverse" : "flex-row"
      )}
    >
      {/* Avatar */}
      <div
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-full mt-0.5",
          isUser ? "bg-indigo-500/30" : "bg-slate-700"
        )}
      >
        {isUser ? (
          <User size={14} className="text-indigo-400" />
        ) : (
          <Bot size={14} className="text-slate-300" />
        )}
      </div>

      {/* Bubble */}
      <div className={cn("flex flex-col gap-1 min-w-0 max-w-[80%]", isUser && "items-end")}>
        <div
          className={cn(
            "rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
            isUser
              ? "bg-indigo-500 text-white rounded-tr-sm"
              : "bg-slate-800 text-slate-100 border border-slate-700 rounded-tl-sm"
          )}
        >
          {message.content}
          {message.isStreaming && !message.content && (
            <span className="inline-flex gap-1 items-center text-slate-400">
              <span className="h-1.5 w-1.5 rounded-full bg-slate-400 animate-bounce [animation-delay:0ms]" />
              <span className="h-1.5 w-1.5 rounded-full bg-slate-400 animate-bounce [animation-delay:150ms]" />
              <span className="h-1.5 w-1.5 rounded-full bg-slate-400 animate-bounce [animation-delay:300ms]" />
            </span>
          )}
          {message.isStreaming && message.content && (
            <span className="inline-block w-0.5 h-4 ml-0.5 bg-indigo-400 animate-pulse align-text-bottom" />
          )}
        </div>

        {/* Tool calls */}
        {message.toolCalls && message.toolCalls.length > 0 && (
          <div className="w-full">
            <ToolCallDisplay toolCalls={message.toolCalls} />
          </div>
        )}
      </div>
    </div>
  );
}
