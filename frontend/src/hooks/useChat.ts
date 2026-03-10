"use client";

import { useState, useCallback, useRef } from "react";
import { generateId } from "@/lib/utils";
import type { ChatMessage, SseEvent, ToolCallData, UsageStats } from "@/types";

interface UseChatOptions {
  tenantId: string;
  userId: string;
  conversationId?: string;
}

interface UseChatReturn {
  messages: ChatMessage[];
  isStreaming: boolean;
  lastUsage: UsageStats | null;
  sendMessage: (content: string) => Promise<void>;
  clearMessages: () => void;
  conversationId: string;
}

export function useChat({
  tenantId,
  userId,
  conversationId: initialConversationId,
}: UseChatOptions): UseChatReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [lastUsage, setLastUsage] = useState<UsageStats | null>(null);
  const conversationIdRef = useRef<string>(initialConversationId ?? generateId());
  const abortControllerRef = useRef<AbortController | null>(null);

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
      }
    },
    [isStreaming, tenantId, userId, handleSseEvent]
  );

  const clearMessages = useCallback(() => {
    setMessages([]);
    conversationIdRef.current = generateId();
  }, []);

  return {
    messages,
    isStreaming,
    lastUsage,
    sendMessage,
    clearMessages,
    conversationId: conversationIdRef.current,
  };
}
