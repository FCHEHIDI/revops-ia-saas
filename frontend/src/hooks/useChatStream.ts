import { useCallback, useEffect, useRef, useState } from "react";
import type { SseEvent, ToolCallData } from "@/types";

interface UseChatStreamOptions {
  url: string;
  onMessage?: (event: SseEvent) => void;
  onError?: (error: unknown) => void;
}

export function useChatStream({ url, onMessage, onError }: UseChatStreamOptions) {
  const [isConnected, setIsConnected] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);

  const close = useCallback(() => {
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
    setIsConnected(false);
  }, []);

  useEffect(() => {
    setIsConnected(false);
    const es = new EventSource(url, { withCredentials: true });
    eventSourceRef.current = es;
    es.onopen = () => setIsConnected(true);
    es.onerror = (err) => {
      setIsConnected(false);
      close();
      if (onError) onError(err);
    };
    es.onmessage = (e) => {
      if (e.data === "[DONE]" || !e.data) return;
      try {
        const event = JSON.parse(e.data) as SseEvent;
        if (onMessage) onMessage(event);
      } catch {}
    };
    return () => {
      es.close();
      setIsConnected(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url]);

  return { isConnected, close };
}
