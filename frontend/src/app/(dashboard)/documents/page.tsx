import { DocumentsUpload } from "@/components/documents/documents-upload";

export default function DocumentsPage() {
  return (
    <div className="flex h-full flex-col">
      {/* ── Hero ── Salle des Manuscrits ── */}
      <div style={{ height: 220, position: "relative", overflow: "hidden", flexShrink: 0 }}>
        {/* Background image */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            backgroundImage: "url('/visuels/documents.png')",
            backgroundSize: "cover",
            backgroundPosition: "center 75%",
            filter: "brightness(0.42) saturate(0.6)",
          }}
        />
        {/* Bottom fade */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            background:
              "linear-gradient(to bottom, rgba(5,5,5,0) 20%, rgba(5,5,5,0.78) 70%, #050505 100%)",
          }}
        />
        {/* Vignette — amber-or gauche + rouge droite */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            background:
              "linear-gradient(to right, rgba(138,88,0,0.28) 0%, transparent 30%, transparent 70%, rgba(138,0,0,0.22) 100%)",
          }}
        />
        {/* Brume basse parchemin */}
        <div
          style={{
            position: "absolute",
            bottom: 0,
            left: 0,
            right: 0,
            height: 70,
            background: "linear-gradient(to top, rgba(60,30,0,0.18) 0%, transparent 100%)",
          }}
        />

        {/* Text overlay */}
        <div
          style={{
            position: "absolute",
            bottom: 28,
            left: 0,
            right: 0,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 6,
          }}
        >
          <span
            className="font-cinzel tracking-[0.25em] uppercase"
            style={{
              fontSize: 10,
              color: "#C07000",
              textShadow: "0 0 18px rgba(192,112,0,0.85), 0 0 40px rgba(192,112,0,0.40)",
              letterSpacing: "0.28em",
            }}
          >
            Salle des Manuscrits
          </span>
          <h1
            className="font-cinzel font-bold text-3xl tracking-[0.08em]"
            style={{
              color: "var(--white-spectral)",
              textShadow:
                "0 0 32px rgba(212,160,0,0.55), 0 2px 8px rgba(5,5,5,0.90)",
            }}
          >
            Documents
          </h1>
          <p
            className="text-xs tracking-[0.15em]"
            style={{
              color: "var(--gray-silver)",
              fontFamily: "var(--font-body)",
            }}
          >
            Indexation &amp; mémoire documentaire
          </p>
        </div>
      </div>

      {/* ── Content ── */}
      <main className="flex-1 overflow-y-auto px-6 py-6">
        <DocumentsUpload />
      </main>
    </div>
  );
}
