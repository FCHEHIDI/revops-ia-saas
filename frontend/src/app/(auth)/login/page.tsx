"use client";

import Image from "next/image";
import { useState, type FormEvent } from "react";
import { useAuth } from "@/hooks/useAuth";

export default function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail]       = useState("");
  const [password, setPassword] = useState("");
  const [error, setError]       = useState("");
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
    <div
      className="relative flex min-h-screen items-center justify-center px-4 overflow-hidden"
      style={{ background: "var(--bg-void)" }}
    >
      {/* Background layers */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background: `
            radial-gradient(ellipse 70% 70% at 15% 50%, rgba(255,0,0,0.05) 0%, transparent 65%),
            radial-gradient(ellipse 60% 60% at 85% 50%, rgba(63,79,255,0.04) 0%, transparent 65%)
          `,
        }}
      />
      {/* Scan line overlay */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background: "repeating-linear-gradient(0deg, transparent, transparent 3px, rgba(0,0,0,0.06) 3px, rgba(0,0,0,0.06) 4px)",
        }}
      />

      {/* Login panel */}
      <div
        className="relative w-full max-w-sm animate-slide-up"
        style={{
          background: "rgba(17,17,17,0.72)",
          backdropFilter: "blur(28px)",
          WebkitBackdropFilter: "blur(28px)",
          border: "1px solid rgba(255,255,255,0.06)",
          borderRadius: "var(--radius-lg)",
          padding: "40px 36px",
          boxShadow: "var(--shadow-deep)",
        }}
      >
        {/* Logo + brand */}
        <div className="mb-8 flex flex-col items-center gap-4">
          <div
            className="flex h-16 w-16 items-center justify-center overflow-hidden rounded-2xl"
            style={{
              background: "rgba(255,0,0,0.08)",
              border: "1px solid rgba(255,0,0,0.2)",
              boxShadow: "0 0 32px rgba(255,0,0,0.1)",
            }}
          >
            <Image src="/favicon.png" alt="ROI" width={48} height={48} className="object-contain" priority />
          </div>
          <div className="text-center">
            <h1
              className="font-orbitron text-xl font-black tracking-widest"
              style={{ color: "var(--text-primary)" }}
            >
              ROI
            </h1>
            <p
              className="mt-1 text-xs font-semibold tracking-widest uppercase"
              style={{ color: "var(--accent-blue)", textShadow: "0 0 20px rgba(63,79,255,0.5)" }}
            >
              REVOPS INTELLIGENCE — The Flow Begins
            </p>
          </div>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Email */}
          <div className="space-y-1.5">
            <label
              htmlFor="email"
              className="block text-xs font-medium tracking-widest uppercase"
              style={{ color: "var(--text-muted)" }}
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
              className="w-full text-sm transition-all duration-200 outline-none"
              style={{
                background: "var(--bg-elevated)",
                border: "1px solid var(--border-default)",
                borderRadius: "var(--radius-input)",
                color: "var(--text-primary)",
                padding: "10px 14px",
              }}
              onFocus={(e) => {
                e.currentTarget.style.border = "1px solid rgba(63,79,255,0.5)";
                e.currentTarget.style.boxShadow = "var(--shadow-blue)";
              }}
              onBlur={(e) => {
                e.currentTarget.style.border = "1px solid var(--border-default)";
                e.currentTarget.style.boxShadow = "none";
              }}
            />
          </div>

          {/* Password */}
          <div className="space-y-1.5">
            <label
              htmlFor="password"
              className="block text-xs font-medium tracking-widest uppercase"
              style={{ color: "var(--text-muted)" }}
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
              className="w-full text-sm transition-all duration-200 outline-none"
              style={{
                background: "var(--bg-elevated)",
                border: "1px solid var(--border-default)",
                borderRadius: "var(--radius-input)",
                color: "var(--text-primary)",
                padding: "10px 14px",
              }}
              onFocus={(e) => {
                e.currentTarget.style.border = "1px solid rgba(63,79,255,0.5)";
                e.currentTarget.style.boxShadow = "var(--shadow-blue)";
              }}
              onBlur={(e) => {
                e.currentTarget.style.border = "1px solid var(--border-default)";
                e.currentTarget.style.boxShadow = "none";
              }}
            />
          </div>

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

          <button
            type="submit"
            disabled={isLoading}
            className="w-full text-sm font-semibold tracking-wider transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
            style={{
              background: isLoading ? "rgba(255,0,0,0.5)" : "var(--accent-red)",
              color: "#fff",
              borderRadius: "var(--radius-btn)",
              padding: "12px 20px",
              border: "none",
              marginTop: "8px",
              boxShadow: "0 0 24px rgba(255,0,0,0.3)",
              cursor: isLoading ? "not-allowed" : "pointer",
            }}
            onMouseEnter={(e) => {
              if (!isLoading) (e.currentTarget as HTMLButtonElement).style.boxShadow = "0 0 36px rgba(255,0,0,0.5)";
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLButtonElement).style.boxShadow = "0 0 24px rgba(255,0,0,0.3)";
            }}
          >
            {isLoading ? "Connexion…" : "Se connecter"}
          </button>
        </form>

        <p
          className="mt-6 text-center text-xs"
          style={{ color: "var(--text-muted)" }}
        >
          En vous connectant, vous acceptez nos conditions d&apos;utilisation.
        </p>
      </div>
    </div>
  );
}

