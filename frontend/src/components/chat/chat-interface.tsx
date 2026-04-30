"use client";

import { useEffect, useRef } from "react";
import Image from "next/image";
import { Trash2 } from "lucide-react";
import { ChatWindow } from "./ChatWindow";
import { MessageInput } from "./message-input";
import { useChat } from "@/hooks/useChat";
import { useAuth } from "@/hooks/useAuth";

const SUGGESTIONS = [
  "Montre-moi les contacts actifs",
  "Quelles factures sont en retard ?",
  "Résume mes métriques du mois",
];

export function ChatInterface() {
  const { user } = useAuth();
  const { messages, isStreaming, sendMessage, clearMessages } = useChat({
    tenantId: user?.tenant_id ?? "",
    userId: user?.id ?? "",
  });

  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div
      className="flex h-full flex-col relative"
      style={{
        background: "radial-gradient(ellipse 80% 60% at 50% 0%, #1a0000 0%, #0a0a0a 55%, #000 100%)",
        border: "1px solid var(--red-dark)",
        borderRadius: "8px",
        overflow: "hidden",
        boxShadow: "inset 0 0 20px #220000, 0 0 12px rgba(255,0,0,0.4)",
        animation: "pulseMarbre 2.4s ease-in-out infinite",
      }}
    >
      {/* Toolbar */}
      <div
        className="relative flex items-center justify-between px-5 py-3 flex-shrink-0"
        style={{ borderBottom: "1px solid var(--chat-tool-divider)", background: "rgba(0,0,0,0.5)", backdropFilter: "blur(12px)" }}
      >
        <div className="flex items-center gap-3">
          {/* Xenito identity */}
          <div className="flex items-center gap-2.5">
            <div
              className="relative flex h-10 w-10 items-center justify-center rounded-lg overflow-hidden"
              style={{
                background: "rgba(0,0,0,0.8)",
                border: "1px solid var(--chat-empty-border)",
                boxShadow: isStreaming ? "0 0 12px rgba(255,0,0,0.4)" : "0 0 6px var(--accent-glow)",
                transition: "box-shadow 0.4s ease",
              }}
            >
              <Image src="/brand/xenito.png" alt="Xenito" width={36} height={36} className="object-contain scale-110" />
            </div>
            <span
              className="font-mono-geist font-medium tracking-widest uppercase"
              style={{ color: "var(--mcp-crm)", fontSize: "11px", letterSpacing: "0.2em" }}
            >
              XENITO
            </span>
          </div>
          {/* AI status indicator */}
          <div className="flex items-center gap-2">
            <div
              className="h-1.5 w-1.5 rounded-full"
              style={{
                background: isStreaming ? "#ff0000" : "#333",
                boxShadow: isStreaming ? "0 0 8px var(--accent-red), 0 0 20px rgba(255,0,0,0.4)" : "none",
                transition: "all 0.3s",
              }}
            />
            <span
              className="font-mono-geist text-xs tracking-widest uppercase"
              style={{ color: isStreaming ? "var(--mcp-crm)" : "var(--text-muted)", fontSize: "10px" }}
            >
              {isStreaming ? "PROCESSING…" : "READY"}
            </span>
          </div>
          {isStreaming && (
            <div className="data-flow-line w-16 rounded-full" />
          )}
        </div>

        <button
          onClick={clearMessages}
          className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs transition-all duration-200"
          style={{ color: "var(--text-muted)", border: "1px solid transparent" }}
          onMouseEnter={(e) => {
            e.currentTarget.style.color = "#ff4444";
            e.currentTarget.style.border = "1px solid var(--chat-tool-border)";
            e.currentTarget.style.background = "var(--chat-tool-bg-hover)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.color = "var(--text-muted)";
            e.currentTarget.style.border = "1px solid transparent";
            e.currentTarget.style.background = "transparent";
          }}
          aria-label="Effacer la conversation"
        >
          <Trash2 size={13} />
          <span className="hidden sm:inline font-mono-geist tracking-wide" style={{ fontSize: "10px", textTransform: "uppercase" }}>
            Clear
          </span>
        </button>
      </div>

      {/* Messages / Empty state */}
      {messages.length === 0 ? (
        <div className="flex-1 chat-scroll flex items-center justify-center p-6">
          <div className="flex flex-col items-center gap-6 text-center max-w-sm msg-enter">
            {/* Xenito avatar orb */}
            <div
              className="relative flex h-20 w-20 items-center justify-center rounded-2xl overflow-hidden"
              style={{
                background: "rgba(0,0,0,0.8)",
                border: "1px solid var(--chat-tool-border)",
                boxShadow: "0 0 40px var(--accent-glow), 0 0 80px rgba(255,0,0,0.06), inset 0 0 20px rgba(255,0,0,0.05)",
              }}
            >
              <Image
                src="/brand/xenito.png"
                alt="Xenito"
                width={72}
                height={72}
                className="object-contain scale-105"
                style={{ filter: "drop-shadow(0 0 12px var(--accent-glow))" }}
              />
            </div>

            <div>
              <p
                className="font-mono-geist font-semibold tracking-widest uppercase text-center"
                style={{ color: "var(--mcp-crm)", fontSize: "13px", letterSpacing: "0.25em" }}
              >
                XENITO
              </p>
              <p className="mt-1 text-sm font-medium text-center" style={{ color: "var(--text-secondary)" }}>
                Bonjour{user ? `, ${user.full_name.split(" ")[0]}` : ""}
              </p>
              <p className="mt-1.5 text-sm leading-relaxed text-center" style={{ color: "var(--text-muted)" }}>
                Interface vivante. Posez une question sur vos contacts,<br />
                factures ou métriques RevOps.
              </p>
            </div>

            {/* Suggestion chips */}
            <div className="flex flex-wrap justify-center gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => sendMessage(s)}
                  disabled={isStreaming}
                  className="rounded-lg px-3 py-1.5 text-xs transition-all duration-200"
                  style={{ color: "var(--text-muted)", border: "1px solid var(--border-default)", background: "rgba(255,255,255,0.02)" }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.color = "var(--text-secondary)";
                    e.currentTarget.style.border = "1px solid var(--chat-empty-border)";
                    e.currentTarget.style.background = "var(--chat-empty-bg)";
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.color = "var(--text-muted)";
                    e.currentTarget.style.border = "1px solid var(--border-default)";
                    e.currentTarget.style.background = "rgba(255,255,255,0.02)";
                  }}
                >
                  {s}
                </button>
              ))}
            </div>

            {/* Signature line */}
            <p className="font-mono-geist text-center" style={{ color: "#333", fontSize: "10px", letterSpacing: "0.12em" }}>
              ROUGE = CONSCIENCE · BLEU = ANALYSE · NOIR = SILENCE
            </p>
          </div>
          <div ref={bottomRef} />
        </div>
      ) : (
        <ChatWindow messages={messages} />
      )}

      {/* Input zone */}
      <div
        className="flex-shrink-0 p-4"
        style={{ borderTop: "1px solid var(--chat-tool-divider)", background: "rgba(0,0,0,0.6)", backdropFilter: "blur(16px)" }}
      >
        <MessageInput onSend={sendMessage} isStreaming={isStreaming} />
        <p
          className="mt-2 text-center font-mono-geist"
          style={{ color: "#333", fontSize: "10px", letterSpacing: "0.08em" }}
        >
          SHIFT+ENTER — nouvelle ligne · ENTER — envoyer
        </p>
      </div>
    </div>
  );
}

