"use client";

import Image from "next/image";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { useAuth } from "@/hooks/useAuth";

const INPUT_BASE: React.CSSProperties = {
  background: "rgba(5,5,5,0.75)",
  border: "1px solid var(--red-dark)",
  borderRadius: "6px",
  color: "var(--white-spectral)",
  padding: "11px 14px",
  width: "100%",
  fontSize: "14px",
  outline: "none",
  transition: "border-color 0.2s ease, box-shadow 0.2s ease",
  fontFamily: "var(--font-body)",
};

function focusRed(e: React.FocusEvent<HTMLInputElement>) {
  e.currentTarget.style.borderColor = "var(--red-glow)";
  e.currentTarget.style.boxShadow = "var(--glow-red)";
}
function blurRed(e: React.FocusEvent<HTMLInputElement>) {
  e.currentTarget.style.borderColor = "var(--red-dark)";
  e.currentTarget.style.boxShadow = "none";
}

export default function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail]         = useState("");
  const [password, setPassword]   = useState("");
  const [error, setError]         = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setIsLoading(true);
    try {
      await login({ email, password });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Identifiants incorrects");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center px-4 overflow-hidden bg-palazzo">

      {/* ── Palazzo background overlay ── */}
      <div className="pointer-events-none absolute inset-0 bg-palazzo-overlay" />

      {/* ── Scan lines ── */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background: "repeating-linear-gradient(0deg, transparent, transparent 3px, rgba(0,0,0,0.05) 3px, rgba(0,0,0,0.05) 4px)",
        }}
      />

      {/* ── Red atmospheric halo (left — serveurs) ── */}
      <div
        className="pointer-events-none absolute"
        style={{
          left: 0, top: "20%", width: "35%", height: "60%",
          background: "radial-gradient(ellipse at left center, rgba(192,0,0,0.12) 0%, transparent 70%)",
        }}
      />

      {/* ── Fumée dynamique au sol ── */}
      <div className="fog-layer" />
      <div className="smoke-layer-2" />
      <div className="smoke-layer-3" />
      <div className="smoke-wisp" />

      {/* ══════════════════════════════════════
          LOGIN PANEL
      ══════════════════════════════════════ */}
      <div
        className="relative w-full max-w-sm z-10"
        style={{
          background: "rgba(5,5,5,0.82)",
          backdropFilter: "blur(32px)",
          WebkitBackdropFilter: "blur(32px)",
          border: "1px solid var(--red-dark)",
          borderRadius: "8px",
          padding: "44px 36px",
          boxShadow: "var(--inner-shadow-dark), 0 0 0 1px rgba(138,0,0,0.2), 0 24px 64px rgba(0,0,0,0.95)",
        }}
      >
        {/* ── Logo + brand ── */}
        <div className="mb-9 flex flex-col items-center gap-5">
          {/* Medallion */}
          <div
            style={{
              width: 90, height: 90,
              borderRadius: "50%",
              background: "radial-gradient(circle at 38% 38%, #C00000, #5a0000)",
              display: "flex", alignItems: "center", justifyContent: "center",
              boxShadow: "var(--inner-shadow-red), var(--glow-red), 0 4px 20px rgba(0,0,0,0.9)",
              border: "1px solid rgba(192,0,0,0.35)",
            }}
          >
            <Image src="/icons/roi-logo-nb.png" alt="ROI" width={58} height={58} className="object-contain" priority />
          </div>

          <div className="text-center">
            <h1
              className="font-cinzel text-2xl font-bold tracking-[0.2em] uppercase"
              style={{
                color: "var(--white-spectral)",
                textShadow: "0 0 20px rgba(192,0,0,0.5)",
              }}
            >
              RevOps Intelligence
            </h1>
            <p
              className="mt-2 text-[11px] font-semibold tracking-[0.3em] uppercase candle-pulse"
              style={{ color: "var(--red-doge)" }}
            >
              The Flow Begins
            </p>
          </div>
        </div>

        {/* ── Form ── */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <label
              htmlFor="email"
              className="block text-[10px] font-semibold tracking-[0.25em] uppercase"
              style={{ color: "var(--gray-silver)" }}
            >
              Email
            </label>
            <input
              id="email"
              type="email"
              placeholder="vous@entreprise.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              required
              style={INPUT_BASE}
              onFocus={focusRed}
              onBlur={blurRed}
            />
          </div>

          <div className="space-y-1.5">
            <label
              htmlFor="password"
              className="block text-[10px] font-semibold tracking-[0.25em] uppercase"
              style={{ color: "var(--gray-silver)" }}
            >
              Mot de passe
            </label>
            <input
              id="password"
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
              style={INPUT_BASE}
              onFocus={focusRed}
              onBlur={blurRed}
            />
          </div>

          {error && (
            <div
              className="rounded px-3 py-2.5 text-sm"
              style={{
                border: "1px solid rgba(192,0,0,0.4)",
                background: "rgba(138,0,0,0.12)",
                color: "#ff6666",
              }}
            >
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={isLoading}
            className="w-full text-sm font-semibold tracking-[0.15em] uppercase transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
            style={{
              background: isLoading
                ? "rgba(192,0,0,0.5)"
                : "linear-gradient(135deg, #C00000 0%, #8A0000 100%)",
              color: "#fff",
              borderRadius: "6px",
              padding: "13px 20px",
              border: "1px solid rgba(192,0,0,0.4)",
              marginTop: "10px",
              boxShadow: "0 0 20px rgba(192,0,0,0.35), var(--inner-shadow-dark)",
              cursor: isLoading ? "not-allowed" : "pointer",
              fontFamily: "var(--font-body)",
            }}
            onMouseEnter={(e) => {
              if (!isLoading) {
                (e.currentTarget as HTMLButtonElement).style.boxShadow =
                  "0 0 36px rgba(255,0,0,0.6), var(--inner-shadow-dark)";
              }
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLButtonElement).style.boxShadow =
                "0 0 20px rgba(192,0,0,0.35), var(--inner-shadow-dark)";
            }}
          >
            {isLoading ? "Connexion…" : "Se connecter"}
          </button>
        </form>

        {/* ── Footer ── */}
        <div
          className="mt-1 w-full"
          style={{ height: "1px", background: "linear-gradient(90deg, transparent, var(--red-dark), transparent)" }}
        />

        <p
          className="mt-5 text-center text-[11px]"
          style={{ color: "var(--text-muted)" }}
        >
          En vous connectant, vous acceptez nos conditions d&apos;utilisation.
        </p>
        <p
          className="mt-2 text-center text-[11px]"
          style={{ color: "var(--gray-silver)" }}
        >
          Pas encore de compte ?{" "}
          <Link
            href="/register"
            className="transition-colors duration-150 hover:opacity-80"
            style={{ color: "var(--red-doge)", fontWeight: 600 }}
          >
            Créer un compte
          </Link>
        </p>
      </div>
    </div>
  );
}

