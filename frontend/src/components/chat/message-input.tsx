"use client";

import { useState, useRef, type KeyboardEvent } from "react";
import { ArrowUp } from "lucide-react";
import { cn } from "@/lib/utils";

interface MessageInputProps {
  onSend: (message: string) => void;
  isStreaming?: boolean;
  placeholder?: string;
}

export function MessageInput({
  onSend,
  isStreaming = false,
  placeholder = "Posez votre question à l'IA RevOps…",
}: MessageInputProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const canSend = value.trim().length > 0 && !isStreaming;

  const handleSend = () => {
    if (!canSend) return;
    onSend(value.trim());
    setValue("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInput = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  };

  return (
    <div
      className={cn(
        "flex items-end gap-2 rounded-xl p-2.5",
        isStreaming && "input-thinking"
      )}
      style={{
        background: "rgba(8,0,0,0.6)",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
        border: "1px solid rgba(255,0,0,0.2)",
        boxShadow: "inset 0 1px 0 rgba(255,255,255,0.03), 0 4px 24px rgba(0,0,0,0.6)",
        transition: "box-shadow 0.3s ease",
      }}
      onFocus={() => {}}
    >
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        onInput={handleInput}
        placeholder={placeholder}
        rows={1}
        disabled={isStreaming}
        className={cn(
          "flex-1 resize-none bg-transparent px-2 py-1 text-sm outline-none",
          "placeholder:opacity-40 disabled:opacity-50 max-h-40 min-h-[36px]",
        )}
        style={{
          color: "#e0e0e0",
          fontFamily: "'Space Grotesk', sans-serif",
          lineHeight: "1.6",
        }}
      />

      {/* Send button */}
      <button
        onClick={handleSend}
        disabled={!canSend}
        className="send-pulse flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-all duration-200"
        style={
          canSend
            ? {
                background: "#ff0000",
                color: "#fff",
                boxShadow: "0 0 14px rgba(255,0,0,0.45)",
                border: "1px solid rgba(255,80,80,0.3)",
              }
            : {
                background: "rgba(255,255,255,0.04)",
                color: "#333",
                border: "1px solid rgba(255,255,255,0.06)",
                cursor: "not-allowed",
              }
        }
        aria-label="Envoyer"
      >
        <ArrowUp size={15} />
      </button>
    </div>
  );
}

