"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import Image from "next/image";
import { Trash2, Plus, MessageSquare, ChevronLeft, ChevronRight } from "lucide-react";
import { ChatWindow } from "./ChatWindow";
import { MessageInput } from "./message-input";
import { useChat } from "@/hooks/useChat";
import { useAuth } from "@/hooks/useAuth";
import { sessionsApi } from "@/lib/api";
import type { Session } from "@/lib/api";
import type { ChatMessage } from "@/types";
import { generateId } from "@/lib/utils";

const SUGGESTIONS = [
  "Montre-moi les contacts actifs",
  "Quelles factures sont en retard ?",
  "Résume mes métriques du mois",
];

function toChatMessages(session: Session): ChatMessage[] {
  return session.messages.map((m) => ({
    id: generateId(),
    role: m.role,
    content: m.content,
    createdAt: m.timestamp ? new Date(m.timestamp) : new Date(),
    isStreaming: false,
    toolCalls: [],
  }));
}

export function ChatInterface() {
  const { user } = useAuth();
  const { messages, isStreaming, sendMessage, clearMessages, loadSession, activeSessionId } = useChat({
    tenantId: user?.tenant_id ?? "",
    userId: user?.id ?? "",
  });

  const bottomRef = useRef<HTMLDivElement>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const refreshSessions = useCallback(async () => {
    try {
      const list = await sessionsApi.list();
      setSessions(list);
    } catch {
      // unauthenticated or network error — ignore
    }
  }, []);

  useEffect(() => {
    if (user) refreshSessions();
  }, [user, refreshSessions]);

  // Refresh sidebar after each streamed exchange
  useEffect(() => {
    if (!isStreaming && activeSessionId) {
      refreshSessions();
      setSelectedId(activeSessionId);
    }
  }, [isStreaming, activeSessionId, refreshSessions]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleNewConversation = () => {
    clearMessages();
    setSelectedId(null);
  };

  const handleSelectSession = async (s: Session) => {
    if (s.id === selectedId) return;
    try {
      const full = await sessionsApi.get(s.id);
      loadSession(full.id, toChatMessages(full));
      setSelectedId(full.id);
    } catch {
      // ignore
    }
  };

  const handleDeleteSession = async (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    try {
      await sessionsApi.delete(sessionId);
      setSessions((prev) => prev.filter((s) => s.id !== sessionId));
      if (selectedId === sessionId) {
        clearMessages();
        setSelectedId(null);
      }
    } catch {
      // ignore
    }
  };

  return (
    <div className="flex h-full overflow-hidden" style={{ borderRadius: "8px" }}>
      {/* ── Sidebar sessions ── */}
      <div
        style={{
          width: sidebarOpen ? 220 : 0,
          minWidth: sidebarOpen ? 220 : 0,
          overflow: "hidden",
          transition: "width 0.25s ease, min-width 0.25s ease",
          background: "rgba(5,0,0,0.85)",
          borderRight: sidebarOpen ? "1px solid var(--red-dark)" : "none",
          display: "flex",
          flexDirection: "column",
        }}
      >
        {/* Sidebar header */}
        <div
          className="flex items-center justify-between px-3 py-3 flex-shrink-0"
          style={{ borderBottom: "1px solid var(--chat-tool-divider)" }}
        >
          <span
            className="font-mono-geist tracking-widest uppercase"
            style={{ color: "var(--text-muted)", fontSize: "9px", letterSpacing: "0.2em" }}
          >
            Conversations
          </span>
          <button
            onClick={handleNewConversation}
            title="Nouvelle conversation"
            className="rounded p-1 transition-colors"
            style={{ color: "var(--text-muted)" }}
            onMouseEnter={(e) => (e.currentTarget.style.color = "var(--mcp-crm)")}
            onMouseLeave={(e) => (e.currentTarget.style.color = "var(--text-muted)")}
          >
            <Plus size={13} />
          </button>
        </div>

        {/* Session list */}
        <div className="flex-1 overflow-y-auto" style={{ scrollbarWidth: "none" }}>
          {sessions.length === 0 ? (
            <p
              className="px-3 py-4 font-mono-geist text-center"
              style={{ color: "#333", fontSize: "10px" }}
            >
              Aucune session
            </p>
          ) : (
            sessions.map((s) => {
              const isActive = s.id === selectedId;
              const label = s.title ?? s.id.slice(0, 12) + "…";
              return (
                <div
                  key={s.id}
                  onClick={() => handleSelectSession(s)}
                  className="group flex items-center gap-2 px-3 py-2.5 cursor-pointer transition-colors"
                  style={{
                    background: isActive ? "rgba(192,0,0,0.10)" : "transparent",
                    borderLeft: isActive ? "2px solid var(--mcp-crm)" : "2px solid transparent",
                  }}
                  onMouseEnter={(e) => {
                    if (!isActive) (e.currentTarget as HTMLElement).style.background = "rgba(255,255,255,0.03)";
                  }}
                  onMouseLeave={(e) => {
                    if (!isActive) (e.currentTarget as HTMLElement).style.background = "transparent";
                  }}
                >
                  <MessageSquare size={11} style={{ color: isActive ? "var(--mcp-crm)" : "var(--text-muted)", flexShrink: 0 }} />
                  <span
                    className="flex-1 truncate font-mono-geist"
                    style={{ fontSize: "11px", color: isActive ? "var(--text-secondary)" : "var(--text-muted)" }}
                    title={label}
                  >
                    {label}
                  </span>
                  <button
                    onClick={(e) => handleDeleteSession(e, s.id)}
                    className="opacity-0 group-hover:opacity-100 transition-opacity rounded p-0.5"
                    style={{ color: "#555" }}
                    onMouseEnter={(e) => (e.currentTarget.style.color = "#ff4444")}
                    onMouseLeave={(e) => (e.currentTarget.style.color = "#555")}
                    title="Supprimer"
                  >
                    <Trash2 size={10} />
                  </button>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* ── Chat panel ── */}
      <div
        className="flex flex-1 flex-col relative"
        style={{
          background: "radial-gradient(ellipse 80% 60% at 50% 0%, #1a0000 0%, #0a0a0a 55%, #000 100%)",
          boxShadow: "inset 0 0 20px #220000, 0 0 12px rgba(255,0,0,0.4)",
          animation: "pulseMarbre 2.4s ease-in-out infinite",
          overflow: "hidden",
        }}
      >
        {/* Toolbar */}
        <div
          className="relative flex items-center justify-between px-5 py-3 flex-shrink-0"
          style={{ borderBottom: "1px solid var(--chat-tool-divider)", background: "rgba(0,0,0,0.5)", backdropFilter: "blur(12px)" }}
        >
          <div className="flex items-center gap-3">
            {/* Sidebar toggle */}
            <button
              onClick={() => setSidebarOpen((v) => !v)}
              className="rounded p-1 transition-colors"
              style={{ color: "var(--text-muted)" }}
              onMouseEnter={(e) => (e.currentTarget.style.color = "var(--text-secondary)")}
              onMouseLeave={(e) => (e.currentTarget.style.color = "var(--text-muted)")}
              title={sidebarOpen ? "Masquer les sessions" : "Afficher les sessions"}
            >
              {sidebarOpen ? <ChevronLeft size={14} /> : <ChevronRight size={14} />}
            </button>
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
            onClick={handleNewConversation}
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
            aria-label="Nouvelle conversation"
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
    </div>
  );
}

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

