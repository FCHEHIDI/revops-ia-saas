"use client";

import Image from "next/image";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { authApi } from "@/lib/api";

export default function RegisterPage() {
  const router = useRouter();
  const [fullName, setFullName]         = useState("");
  const [companyName, setCompanyName]   = useState("");
  const [email, setEmail]               = useState("");
  const [password, setPassword]         = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError]               = useState("");
  const [isLoading, setIsLoading]       = useState(false);

  const INPUT_BASE: React.CSSProperties = {
    background: "rgba(10,10,10,0.7)",
    border: "1px solid var(--red-dark)",
    borderRadius: "8px",
    color: "var(--white-spectral)",
    padding: "10px 14px",
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");

    if (password !== confirmPassword) {
      setError("Les mots de passe ne correspondent pas.");
      return;
    }
    if (password.length < 8) {
      setError("Le mot de passe doit contenir au moins 8 caractères.");
      return;
    }

    setIsLoading(true);
    try {
      await authApi.register({
        email,
        password,
        full_name: fullName,
        company_name: companyName || undefined,
      });
      router.push("/chat");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Impossible de créer le compte. Réessayez."
      );
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="bg-palazzo relative flex min-h-screen items-center justify-center px-4 overflow-hidden">
      {/* Dark overlay */}
      <div className="bg-palazzo-overlay pointer-events-none absolute inset-0" />

      {/* Scan lines */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "repeating-linear-gradient(0deg, transparent, transparent 3px, rgba(0,0,0,0.07) 3px, rgba(0,0,0,0.07) 4px)",
          zIndex: 1,
        }}
      />

      {/* Red corner halos */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse 60% 50% at 5% 50%, rgba(138,0,0,0.18) 0%, transparent 70%)",
          zIndex: 1,
        }}
      />

      {/* Fog */}
      <div className="fog-layer" style={{ zIndex: 2 }} />

      {/* Panel */}
      <div
        className="relative w-full max-w-sm animate-slide-up"
        style={{
          zIndex: 10,
          background: "rgba(5,5,5,0.82)",
          backdropFilter: "blur(28px)",
          WebkitBackdropFilter: "blur(28px)",
          border: "1px solid var(--red-dark)",
          borderRadius: "16px",
          padding: "40px 36px",
          boxShadow: "var(--inner-shadow-dark), 0 0 60px rgba(0,0,0,0.9)",
        }}
      >
        {/* Médaillon + brand */}
        <div className="mb-8 flex flex-col items-center gap-4">
          {/* Médaillon */}
          <div
            style={{
              width: 72, height: 72,
              borderRadius: "50%",
              background: "radial-gradient(circle at 40% 35%, #8A0000, #220000)",
              border: "2px solid var(--red-dark)",
              boxShadow: "var(--glow-red-strong), var(--inner-shadow-red)",
              display: "flex", alignItems: "center", justifyContent: "center",
            }}
          >
            <Image
              src="/favicon.png"
              alt="ROI"
              width={48}
              height={48}
              className="object-contain"
              priority
            />
          </div>
          <div className="text-center">
            <h1
              className="font-cinzel text-2xl font-bold tracking-widest"
              style={{
                color: "var(--white-spectral)",
                textShadow: "0 0 18px rgba(192,0,0,0.5)",
              }}
            >
              RevOps Intelligence
            </h1>
            <p
              className="mt-1 text-xs font-semibold tracking-widest uppercase candle-pulse"
              style={{ color: "var(--red-doge)" }}
            >
              Créez votre espace de travail
            </p>
          </div>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Full name */}
          <Field label="Nom complet">
            <input
              id="full_name"
              type="text"
              placeholder="Jane Dupont"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              autoComplete="name"
              required
              className="w-full text-sm transition-all duration-200 outline-none"
              style={INPUT_BASE}
              onFocus={focusRed}
              onBlur={blurRed}
            />
          </Field>

          {/* Company name */}
          <Field label="Entreprise (optionnel)">
            <input
              id="company_name"
              type="text"
              placeholder="Acme RevOps"
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              autoComplete="organization"
              className="w-full text-sm transition-all duration-200 outline-none"
              style={INPUT_BASE}
              onFocus={focusRed}
              onBlur={blurRed}
            />
          </Field>

          {/* Email */}
          <Field label="Email">
            <input
              id="email"
              type="email"
              placeholder="vous@entreprise.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              required
              className="w-full text-sm transition-all duration-200 outline-none"
              style={INPUT_BASE}
              onFocus={focusRed}
              onBlur={blurRed}
            />
          </Field>

          {/* Password */}
          <Field label="Mot de passe">
            <input
              id="password"
              type="password"
              placeholder="8 caractères minimum"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
              required
              minLength={8}
              className="w-full text-sm transition-all duration-200 outline-none"
              style={INPUT_BASE}
              onFocus={focusRed}
              onBlur={blurRed}
            />
          </Field>

          {/* Confirm password */}
          <Field label="Confirmer le mot de passe">
            <input
              id="confirm_password"
              type="password"
              placeholder="••••••••"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              autoComplete="new-password"
              required
              className="w-full text-sm transition-all duration-200 outline-none"
              style={INPUT_BASE}
              onFocus={focusRed}
              onBlur={blurRed}
            />
          </Field>

          {/* Inline error */}
          {error && (
            <div
              className="rounded-lg px-3 py-2.5 text-sm"
              style={{
                border: "1px solid rgba(255,0,0,0.3)",
                background: "rgba(255,0,0,0.06)",
                color: "var(--accent-red)",
              }}
            >
              {error}
            </div>
          )}

          {/* Submit */}
          <button
            type="submit"
            disabled={isLoading}
            className="w-full font-cinzel text-sm tracking-[0.15em] uppercase font-semibold transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
            style={{
              background: isLoading
                ? "rgba(138,0,0,0.5)"
                : "linear-gradient(135deg, #C00000, #8A0000)",
              color: "var(--white-spectral)",
              borderRadius: "8px",
              padding: "13px 20px",
              border: "1px solid var(--red-dark)",
              marginTop: "8px",
              boxShadow: "0 0 24px rgba(192,0,0,0.35)",
              cursor: isLoading ? "not-allowed" : "pointer",
            }}
            onMouseEnter={(e) => {
              if (!isLoading) {
                (e.currentTarget as HTMLButtonElement).style.boxShadow =
                  "var(--glow-red-strong)";
                (e.currentTarget as HTMLButtonElement).style.background =
                  "linear-gradient(135deg, #E00000, #C00000)";
              }
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLButtonElement).style.boxShadow =
                "0 0 24px rgba(192,0,0,0.35)";
              (e.currentTarget as HTMLButtonElement).style.background =
                "linear-gradient(135deg, #C00000, #8A0000)";
            }}
          >
            {isLoading ? "Création en cours…" : "Créer mon compte"}
          </button>
        </form>

        {/* Séparateur */}
        <div
          style={{
            margin: "20px 0 16px",
            height: 1,
            background: "linear-gradient(90deg, transparent, var(--red-dark), transparent)",
          }}
        />

        {/* Link to login */}
        <p
          className="text-center text-xs"
          style={{ color: "var(--gray-silver)" }}
        >
          Déjà un compte ?{" "}
          <Link
            href="/login"
            className="transition-colors duration-150"
            style={{ color: "var(--red-doge)" }}
            onMouseEnter={(e) => { (e.currentTarget as HTMLAnchorElement).style.color = "var(--red-glow)"; }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLAnchorElement).style.color = "var(--red-doge)"; }}
          >
            Se connecter
          </Link>
        </p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Local helpers (avoid repetition in event handlers)
// ---------------------------------------------------------------------------

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label
        className="block text-xs font-medium tracking-widest uppercase"
        style={{ color: "var(--gray-silver)" }}
      >
        {label}
      </label>
      {children}
    </div>
  );
}

function focusRed(e: React.FocusEvent<HTMLInputElement>) {
  e.currentTarget.style.border = "1px solid var(--red-doge)";
  e.currentTarget.style.boxShadow = "var(--glow-red)";
}

function blurRed(e: React.FocusEvent<HTMLInputElement>) {
  e.currentTarget.style.border = "1px solid var(--red-dark)";
  e.currentTarget.style.boxShadow = "none";
}
