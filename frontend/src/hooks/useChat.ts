"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { generateId } from "@/lib/utils";
import { sessionsApi } from "@/lib/api";
import type { ChatMessage, SseEvent, ToolCallData, UsageStats } from "@/types";

interface UseChatOptions {
  tenantId: string;
  userId: string;
  conversationId?: string;
}

function storageKey(tenantId: string, userId: string) {
  return `xenito_chat_${tenantId}_${userId}`;
}

function loadPersistedState(tenantId: string, userId: string): { messages: ChatMessage[]; conversationId: string } {
  if (typeof window === "undefined" || !tenantId || !userId) {
    return { messages: [], conversationId: generateId() };
  }
  try {
    const raw = localStorage.getItem(storageKey(tenantId, userId));
    if (!raw) return { messages: [], conversationId: generateId() };
    const parsed = JSON.parse(raw) as { messages: ChatMessage[]; conversationId: string };
    // Rehydrate Date objects
    const messages = parsed.messages.map((m) => ({
      ...m,
      createdAt: new Date(m.createdAt),
      isStreaming: false, // never persist a streaming state
    }));
    return { messages, conversationId: parsed.conversationId ?? generateId() };
  } catch {
    return { messages: [], conversationId: generateId() };
  }
}

interface UseChatReturn {
  messages: ChatMessage[];
  isStreaming: boolean;
  lastUsage: UsageStats | null;
  sendMessage: (content: string) => Promise<void>;
  clearMessages: () => void;
  loadSession: (sessionId: string, sessionMessages: ChatMessage[]) => void;
  conversationId: string;
  activeSessionId: string | null;
}

export function useChat({
  tenantId,
  userId,
  conversationId: initialConversationId,
}: UseChatOptions): UseChatReturn {
  // Start empty — we'll hydrate from localStorage once tenantId/userId are available
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [lastUsage, setLastUsage] = useState<UsageStats | null>(null);
  const conversationIdRef = useRef<string>(initialConversationId ?? generateId());
  const hydratedRef = useRef(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  // Tracks the backend session ID for server-side persistence
  const sessionIdRef = useRef<string | null>(null);

  // Hydrate from localStorage as soon as tenantId + userId are known (only once)
  useEffect(() => {
    if (hydratedRef.current || !tenantId || !userId) return;
    hydratedRef.current = true;
    const saved = loadPersistedState(tenantId, userId);
    if (saved.messages.length > 0) {
      setMessages(saved.messages);
    }
    if (!initialConversationId) {
      conversationIdRef.current = saved.conversationId;
    }
  }, [tenantId, userId, initialConversationId]);

  // Persist messages + conversationId to localStorage whenever they change
  useEffect(() => {
    if (!tenantId || !userId) return;
    try {
      localStorage.setItem(
        storageKey(tenantId, userId),
        JSON.stringify({ messages, conversationId: conversationIdRef.current })
      );
    } catch {
      // quota exceeded or SSR — ignore
    }
  }, [messages, tenantId, userId]);

  // ---------------------------------------------------------------------------
  // 1) handleSseEvent REMONTÉ AVANT sendMessage → dépendances OK
  // ---------------------------------------------------------------------------
  const handleSseEvent = useCallback(
    (event: SseEvent, assistantMessageId: string) => {
      switch (event.type) {
        case "token":
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMessageId
                ? { ...m, content: m.content + event.content }
                : m
            )
          );
          break;

        case "tool_call": {
          const toolCall: ToolCallData = { tool: event.tool, result: event.result };
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMessageId
                ? { ...m, toolCalls: [...(m.toolCalls ?? []), toolCall] }
                : m
            )
          );
          break;
        }

        case "done":
          setLastUsage(event.usage);
          break;

        case "error":
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMessageId
                ? {
                    ...m,
                    content: `Erreur : ${event.message}`,
                    isStreaming: false,
                  }
                : m
            )
          );
          break;
      }
    },
    [] // aucune dépendance → stable
  );

  // ---------------------------------------------------------------------------
  // 2) sendMessage → dépendances correctes (inclut handleSseEvent)
  // ---------------------------------------------------------------------------
  const sendMessage = useCallback(
    async (content: string) => {
      if (isStreaming) return;

      const userMessage: ChatMessage = {
        id: generateId(),
        role: "user",
        content,
        createdAt: new Date(),
      };

      const assistantMessageId = generateId();
      const assistantMessage: ChatMessage = {
        id: assistantMessageId,
        role: "assistant",
        content: "",
        toolCalls: [],
        isStreaming: true,
        createdAt: new Date(),
      };

      setMessages((prev) => [...prev, userMessage, assistantMessage]);
      setIsStreaming(true);

      abortControllerRef.current = new AbortController();

      // Ensure we have a backend session for cross-device persistence
      if (!sessionIdRef.current) {
        try {
          const session = await sessionsApi.create(content.slice(0, 80) || undefined);
          sessionIdRef.current = session.id;
          // Align conversation_id with the server session id
          conversationIdRef.current = session.id;
        } catch {
          // non-fatal — streaming still works without persistence
        }
      }

      // Accumulate assistant tokens for end-of-stream persistence
      let assistantContent = "";

      try {
        const res = await fetch("/api/chat/stream", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            tenant_id: tenantId,
            conversation_id: conversationIdRef.current,
            message: content,
            user_id: userId,
          }),
          signal: abortControllerRef.current.signal,
        });

        if (!res.ok || !res.body) {
          throw new Error(`Stream error: ${res.status}`);
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            const data = line.slice(6).trim();
            if (data === "[DONE]" || data === "") continue;

            try {
              const event = JSON.parse(data) as SseEvent;
              handleSseEvent(event, assistantMessageId);
              if (event.type === "token") {
                assistantContent += (event as { type: "token"; content: string }).content ?? "";
              }
            } catch {
              // ignore malformed lines
            }
          }
        }
      } catch (err) {
        if (err instanceof Error && err.name === "AbortError") return;
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMessageId
              ? {
                  ...m,
                  content: m.content || "Une erreur est survenue.",
                  isStreaming: false,
                }
              : m
          )
        );
      } finally {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMessageId ? { ...m, isStreaming: false } : m
          )
        );
        setIsStreaming(false);
        // Persist the exchange server-side (best-effort, non-blocking)
        if (sessionIdRef.current && assistantContent) {
          sessionsApi
            .persistMessages(sessionIdRef.current, [
              { role: "user", content, timestamp: userMessage.createdAt.toISOString() },
              { role: "assistant", content: assistantContent, timestamp: new Date().toISOString() },
            ])
            .catch(() => {
              // non-fatal — message already in localStorage
            });
        }
      }
    },
    [isStreaming, tenantId, userId, handleSseEvent]
  );

  const clearMessages = useCallback(() => {
    setMessages([]);
    conversationIdRef.current = generateId();
    sessionIdRef.current = null;
    try {
      localStorage.removeItem(storageKey(tenantId, userId));
    } catch {
      // ignore
    }
  }, [tenantId, userId]);

  const loadSession = useCallback(
    (sessionId: string, sessionMessages: ChatMessage[]) => {
      sessionIdRef.current = sessionId;
      conversationIdRef.current = sessionId;
      setMessages(sessionMessages);
    },
    []
  );

  return {
    messages,
    isStreaming,
    lastUsage,
    sendMessage,
    clearMessages,
    loadSession,
    conversationId: conversationIdRef.current,
    activeSessionId: sessionIdRef.current,
  };
}
