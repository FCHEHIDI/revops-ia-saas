"use client";

import { useEffect, useRef } from "react";
import { Trash2 } from "lucide-react";
import { MessageBubble } from "./message-bubble";
import { MessageInput } from "./message-input";
import { Button } from "@/components/ui/button";
import { useChat } from "@/hooks/useChat";
import { useAuth } from "@/hooks/useAuth";

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
    <div className="flex h-full flex-col">
      {/* Toolbar */}
      <div className="flex items-center justify-between border-b border-slate-700 px-4 py-2.5">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-slate-300">Nouvelle conversation</span>
          {isStreaming && (
            <span className="flex items-center gap-1 text-xs text-indigo-400">
              <span className="h-1.5 w-1.5 rounded-full bg-indigo-400 animate-pulse" />
              L'IA répond…
            </span>
          )}
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={clearMessages}
          className="text-slate-500 hover:text-red-400"
        >
          <Trash2 size={14} />
          Effacer
        </Button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {messages.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-indigo-500/10 border border-indigo-500/20">
              <svg className="h-7 w-7 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
              </svg>
            </div>
            <div>
              <p className="text-slate-300 font-medium">Bonjour{user ? `, ${user.full_name.split(" ")[0]}` : ""} !</p>
              <p className="mt-1 text-sm text-slate-500">
                Je suis votre assistant RevOps. Posez-moi une question sur vos contacts, factures ou métriques.
              </p>
            </div>
            <div className="flex flex-wrap justify-center gap-2 mt-2">
              {[
                "Montre-moi les contacts actifs",
                "Quelles factures sont en retard ?",
                "Résume mes métriques du mois",
              ].map((suggestion) => (
                <button
                  key={suggestion}
                  onClick={() => sendMessage(suggestion)}
                  disabled={isStreaming}
                  className="rounded-full border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-400 hover:border-indigo-500 hover:text-indigo-400 transition-colors"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="border-t border-slate-700 p-4">
        <MessageInput onSend={sendMessage} isStreaming={isStreaming} />
        <p className="mt-2 text-center text-xs text-slate-600">
          Shift+Entrée pour aller à la ligne · Entrée pour envoyer
        </p>
      </div>
    </div>
  );
}
