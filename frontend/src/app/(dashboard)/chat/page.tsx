import { ChatInterface } from "@/components/chat/chat-interface";

export default function ChatPage() {
  return (
    <div className="flex h-full flex-col">

      {/* ── Hero — Salle du Guide ── */}
      <div style={{ height: 220, position: "relative", overflow: "hidden", flexShrink: 0 }}>
        {/* Image de fond palazzo */}
        <div style={{
          position: "absolute", inset: 0,
          backgroundImage: "url('/background.png')",
          backgroundSize: "cover", backgroundPosition: "center 28%",
          filter: "brightness(0.38) saturate(0.58)",
        }} />
        {/* Dégradé bas */}
        <div style={{
          position: "absolute", inset: 0,
          background: "linear-gradient(to bottom, rgba(5,5,5,0) 25%, rgba(5,5,5,0.80) 75%, #050505 100%)",
        }} />
        {/* Vignettes latérales — rouge vif gauche, rouge sombre droite */}
        <div style={{
          position: "absolute", inset: 0,
          background: "linear-gradient(to right, rgba(192,0,0,0.28) 0%, transparent 30%, transparent 70%, rgba(138,0,0,0.24) 100%)",
        }} />
        {/* Brume de sol rouge */}
        <div style={{
          position: "absolute", bottom: 0, left: 0, right: 0, height: 90,
          background: "linear-gradient(to top, rgba(80,0,0,0.22), transparent)",
        }} />

        {/* Labels — ancrés en bas, identique aux autres salles */}
        <div style={{ position: "absolute", bottom: 28, left: 0, right: 0, display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
          <span
            className="font-cinzel tracking-[0.25em] uppercase"
            style={{ fontSize: 10, color: "#C00000", textShadow: "0 0 18px rgba(192,0,0,0.90), 0 0 42px rgba(192,0,0,0.45)", letterSpacing: "0.28em" }}
          >
            Salle du Guide
          </span>
          <h1
            className="font-cinzel font-bold text-3xl tracking-[0.08em]"
            style={{ color: "var(--white-spectral)", textShadow: "0 0 24px rgba(192,0,0,0.50), 0 2px 8px rgba(0,0,0,0.9)" }}
          >
            XENITO
          </h1>
          <p className="text-xs tracking-[0.15em]" style={{ color: "var(--gray-silver)", fontFamily: "var(--font-body)" }}>
            Xenito · intelligence vivante · conseil stratégique RevOps
          </p>
        </div>
      </div>

      {/* ── Interface de conversation ── */}
      <div className="flex-1 overflow-hidden" style={{ padding: "0 16px 16px 16px" }}>
        <ChatInterface />
      </div>
    </div>
  );
}
