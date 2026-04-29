import Image from "next/image";
import { User } from "lucide-react";
import { cn } from "@/lib/utils";
import { ToolCallDisplay } from "./tool-call-display";
import type { ChatMessage } from "@/types";

interface MessageBubbleProps {
  message: ChatMessage;
}

/* Format time — Geist Mono style */
function MsgTime() {
  const t = new Date().toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
  return (
    <span
      className="font-mono-geist select-none"
      style={{ fontSize: "10px", color: "#444", letterSpacing: "0.06em" }}
    >
      {t}
    </span>
  );
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div
      className={cn("msg-enter flex gap-3 max-w-full", isUser ? "flex-row-reverse" : "flex-row")}
    >
      {/* Avatar */}
      {isUser ? (
        <div
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg mt-1"
          style={{ background: "rgba(255,0,0,0.08)", border: "1px solid rgba(255,0,0,0.3)" }}
        >
          <User size={13} style={{ color: "#ff3333" }} />
        </div>
      ) : (
        <div
          className="relative flex h-8 w-8 shrink-0 items-center justify-center rounded-lg mt-0.5 overflow-hidden"
          style={{
            background: "rgba(0,0,0,0.7)",
            border: "1px solid rgba(255,0,0,0.25)",
            boxShadow: "0 0 10px rgba(255,0,0,0.15)",
          }}
        >
          <Image
            src="/brand/xenito.png"
            alt="Xenito"
            width={28}
            height={28}
            className="object-contain scale-110"
            style={{ filter: "drop-shadow(0 0 4px rgba(255,0,0,0.5))" }}
          />
        </div>
      )}

      {/* Content column */}
      <div className={cn("flex flex-col gap-1.5 min-w-0 max-w-[78%]", isUser && "items-end")}>
        <div
          className="rounded-xl px-4 py-3 text-sm leading-relaxed"
          style={
            isUser
              ? {
                  background: "rgba(20,0,0,0.7)",
                  border: "1px solid rgba(255,51,51,0.22)",
                  boxShadow: "inset 0 1px 0 rgba(255,80,80,0.06), 0 2px 12px rgba(0,0,0,0.6)",
                  color: "#ff6666",
                  backdropFilter: "blur(12px)",
                  borderRadius: "10px 10px 2px 10px",
                }
              : {
                  background: "rgba(255,255,255,0.03)",
                  border: "1px solid rgba(255,255,255,0.07)",
                  boxShadow: "inset 0 1px 0 rgba(255,255,255,0.03), 0 2px 16px rgba(0,0,0,0.7)",
                  color: "#e0e0e0",
                  backdropFilter: "blur(12px)",
                  borderRadius: "10px 10px 10px 2px",
                }
          }
        >
          {message.content}

          {/* Typing dots when streaming but no content yet */}
          {message.isStreaming && !message.content && (
            <span className="inline-flex gap-1.5 items-center">
              {[0, 150, 300].map((delay) => (
                <span
                  key={delay}
                  className="h-1.5 w-1.5 rounded-full animate-bounce"
                  style={{ background: "rgba(255,80,80,0.6)", animationDelay: `${delay}ms` }}
                />
              ))}
            </span>
          )}

          {/* Streaming cursor when content is flowing */}
          {message.isStreaming && message.content && (
            <span
              className="inline-block w-0.5 h-3.5 ml-0.5 align-text-bottom animate-pulse"
              style={{ background: "#ff3333", boxShadow: "0 0 6px rgba(255,0,0,0.6)" }}
            />
          )}
        </div>

        {/* Timestamp */}
        {!message.isStreaming && <MsgTime />}

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

