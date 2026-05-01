import { SequencesList } from "@/components/sequences/sequences-list";

export default function SequencesPage() {
  return (
    <div className="flex h-full flex-col">

      {/* ── Hero — Salle des Rituels ── */}
      <div style={{ height: 220, position: "relative", overflow: "hidden", flexShrink: 0 }}>
        {/* Image de fond */}
        <div style={{
          position: "absolute", inset: 0,
          backgroundImage: "url('/visuels/sequences.png')",
          backgroundSize: "cover", backgroundPosition: "center 75%",
          filter: "brightness(0.45) saturate(0.65)",
        }} />
        {/* Dégradé bas */}
        <div style={{
          position: "absolute", inset: 0,
          background: "linear-gradient(to bottom, rgba(5,5,5,0) 25%, rgba(5,5,5,0.80) 75%, #050505 100%)",
        }} />
        {/* Vignettes latérales — améthyste gauche, rouge droite */}
        <div style={{
          position: "absolute", inset: 0,
          background: "linear-gradient(to right, rgba(80,20,128,0.30) 0%, transparent 28%, transparent 72%, rgba(138,0,0,0.22) 100%)",
        }} />
        {/* Brume de sol */}
        <div style={{
          position: "absolute", bottom: 0, left: 0, right: 0, height: 80,
          background: "linear-gradient(to top, rgba(40,0,80,0.18), transparent)",
        }} />

        {/* Labels */}
        <div style={{ position: "absolute", bottom: 28, left: 0, right: 0, display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
          <span
            className="font-cinzel tracking-[0.25em] uppercase"
            style={{ fontSize: 10, color: "#9B4FD4", textShadow: "0 0 18px rgba(155,79,212,0.85), 0 0 40px rgba(155,79,212,0.40)", letterSpacing: "0.28em" }}
          >
            Salle des Rituels
          </span>
          <h1
            className="font-cinzel font-bold text-3xl tracking-[0.08em]"
            style={{ color: "var(--white-spectral)", textShadow: "0 0 24px rgba(155,79,212,0.45), 0 2px 8px rgba(0,0,0,0.9)" }}
          >
            Séquences
          </h1>
          <p className="text-xs tracking-[0.15em]" style={{ color: "var(--gray-silver)", fontFamily: "var(--font-body)" }}>
            Rituels d&apos;activation · prospection · rétention
          </p>
        </div>
      </div>

      {/* ── Contenu ── */}
      <main className="flex-1 overflow-y-auto px-6 py-6">
        <SequencesList />
      </main>
    </div>
  );
}
