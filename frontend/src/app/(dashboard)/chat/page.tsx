import { Header } from "@/components/layout/header";
import { ChatInterface } from "@/components/chat/chat-interface";

export default function ChatPage() {
  return (
    <div className="flex h-full flex-col">
      <Header title="Chat IA" />
      <div className="flex-1 overflow-hidden">
        <ChatInterface />
      </div>
    </div>
  );
}
