"use client";
import { useRef, useEffect } from "react";
import { MessageBubble } from "./message-bubble";
import type { ChatMessage } from "@/types";

export function ChatWindow({ messages }: { messages: ChatMessage[] }) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="relative flex-1 overflow-hidden">
      {/* Top fade */}
      <div
        className="pointer-events-none absolute inset-x-0 top-0 z-10 h-8"
        style={{ background: "linear-gradient(to bottom, rgba(10,0,0,0.6), transparent)" }}
      />
      {/* Bottom fade */}
      <div
        className="pointer-events-none absolute inset-x-0 bottom-0 z-10 h-8"
        style={{ background: "linear-gradient(to top, rgba(0,0,0,0.7), transparent)" }}
      />

      <div className="chat-scroll h-full px-5 py-5 space-y-5">
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
