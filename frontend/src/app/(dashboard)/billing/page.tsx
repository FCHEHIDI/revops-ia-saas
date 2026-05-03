import Image from "next/image";
import { InvoicesList } from "@/components/billing/invoices-list";

export default function BillingPage() {
  return (
    <div className="flex h-full flex-col" style={{ background: "var(--black-palazzo)" }}>

      {/* ─── Hero : Salle des Comptes ─── */}
      <div style={{ height: 220, position: "relative", overflow: "hidden", flexShrink: 0 }}>
        {/* Photo de fond */}
        <div style={{
          position: "absolute", inset: 0,
          backgroundImage: "url('/visuels/billing.png')",
          backgroundSize: "cover",
          backgroundPosition: "center 62%",
          filter: "brightness(0.45) saturate(0.6)",
        }} />
        {/* Gradient bas */}
        <div style={{
          position: "absolute", inset: 0,
          background: "linear-gradient(to bottom, rgba(5,5,5,0) 25%, rgba(5,5,5,0.85) 75%, #050505 100%)",
        }} />
        {/* Vignette latérale or/rouge */}
        <div style={{
          position: "absolute", inset: 0,
          background: "linear-gradient(to right, rgba(138,80,0,0.22) 0%, transparent 28%, transparent 72%, rgba(138,0,0,0.22) 100%)",
        }} />
        {/* Brume de sol */}
        <div style={{
          position: "absolute", bottom: 0, left: 0, right: 0, height: 60,
          background: "linear-gradient(to top, rgba(80,30,0,0.18) 0%, transparent 100%)",
        }} />
        {/* ── Icône décorative filigrane ── */}
        <Image
          src="/icons/facturation-icon.png"
          alt=""
          aria-hidden="true"
          width={780}
          height={780}
          style={{
            position: "absolute",
            right: "4%",
            top: "50%",
            transform: "translateY(-50%)",
            width: 780,
            height: 780,
            objectFit: "contain",
            opacity: 0.35,
            filter: "blur(0.3px)",
            pointerEvents: "none",
          }}
        />
        {/* Textes */}
        <div style={{ position: "absolute", bottom: 28, left: 0, right: 0, display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
          <span
            className="font-cinzel tracking-[0.35em] uppercase text-xs"
            style={{ color: "#C07000", textShadow: "0 0 20px rgba(192,112,0,0.9)" }}
          >
            Salle des Comptes
          </span>
          <h1
            className="font-cinzel font-bold text-3xl tracking-[0.08em]"
            style={{ color: "var(--white-spectral)", textShadow: "0 0 24px rgba(192,112,0,0.45), 0 2px 8px rgba(0,0,0,0.9)" }}
          >
            Facturation
          </h1>
          <p className="text-xs tracking-[0.15em]" style={{ color: "var(--gray-silver)", fontFamily: "var(--font-body)" }}>
            Registre des factures · paiements · trésorerie
          </p>
        </div>
      </div>

      {/* ─── Contenu ─── */}
      <main className="flex-1 overflow-y-auto px-6 py-6">
        <InvoicesList />
      </main>
    </div>
  );
}
