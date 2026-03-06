"use client";

import { useState, useRef, type KeyboardEvent } from "react";
import { Send } from "lucide-react";
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

  const handleSend = () => {
    const trimmed = value.trim();
    if (!trimmed || isStreaming) return;
    onSend(trimmed);
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
    <div className="flex items-end gap-2 rounded-2xl border border-slate-700 bg-slate-800 p-2 focus-within:border-indigo-500 transition-colors">
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
          "flex-1 resize-none bg-transparent px-2 py-1 text-sm text-slate-100 outline-none",
          "placeholder:text-slate-500 disabled:opacity-50 max-h-40 min-h-[36px]"
        )}
      />
      <button
        onClick={handleSend}
        disabled={!value.trim() || isStreaming}
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-xl transition-all",
          value.trim() && !isStreaming
            ? "bg-indigo-500 text-white hover:bg-indigo-600"
            : "bg-slate-700 text-slate-500 cursor-not-allowed"
        )}
        aria-label="Envoyer"
      >
        <Send size={14} />
      </button>
    </div>
  );
}
