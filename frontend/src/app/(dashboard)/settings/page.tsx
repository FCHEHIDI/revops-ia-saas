"use client";

import { useState } from "react";
import { authApi } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import type { MFASetupResponse } from "@/types";

export default function SettingsPage() {
  const { user, isLoading, refetch } = useAuth();
  const [setupData, setSetupData] = useState<MFASetupResponse | null>(null);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleMfaSetup = async () => {
    setStatus("");
    setIsSubmitting(true);
    try {
      const data = await authApi.setupMfa();
      setSetupData(data);
      setStatus("QR code généré. Scannez-le puis validez le code dans le champ ci-dessous.");
    } catch (err) {
      setStatus(err instanceof Error ? err.message : "Impossible de générer le setup MFA.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleEnable = async () => {
    setStatus("");
    if (!code.match(/^\d{6}$/)) {
      setStatus("Veuillez saisir un code à 6 chiffres.");
      return;
    }
    setIsSubmitting(true);
    try {
      await authApi.enableMfa(code);
      await refetch();
      setSetupData(null);
      setCode("");
      setStatus("MFA activé avec succès.");
    } catch (err) {
      setStatus(err instanceof Error ? err.message : "Échec de l'activation du MFA.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDisable = async () => {
    setStatus("");
    if (!code.match(/^\d{6}$/)) {
      setStatus("Veuillez saisir un code à 6 chiffres.");
      return;
    }
    if (!password) {
      setStatus("Le mot de passe est requis pour désactiver le MFA.");
      return;
    }
    setIsSubmitting(true);
    try {
      await authApi.disableMfa({ password, code });
      await refetch();
      setPassword("");
      setCode("");
      setStatus("MFA désactivé. Votre compte est maintenant protégé par mot de passe uniquement.");
    } catch (err) {
      setStatus(err instanceof Error ? err.message : "Échec de la désactivation du MFA.");
    } finally {
      setIsSubmitting(false);
    }
  };

  if (isLoading || !user) {
    return (
      <div className="p-8 text-sm text-white">Chargement des paramètres de sécurité…</div>
    );
  }

  const qrUrl = setupData
    ? `https://api.qrserver.com/v1/create-qr-code/?data=${encodeURIComponent(setupData.otpauth_uri)}&size=260x260`
    : undefined;

  return (
    <div className="space-y-8 p-8 text-white">
      <div>
        <h1 className="text-2xl font-bold tracking-[0.22em] uppercase" style={{ color: "var(--white-spectral)" }}>
          Sécurité du compte
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-gray-300">
          Gérez l&apos;authentification multifacteur pour renforcer la protection de votre session.
        </p>
      </div>

      <section className="rounded-3xl border border-red-900/70 bg-black/70 p-6 shadow-[0_0_40px_rgba(192,0,0,0.15)]">
        <div className="flex flex-col gap-2">
          <p className="text-sm font-semibold uppercase tracking-[0.2em] text-red-doge">Authentification multifacteur</p>
          <p className="text-sm text-gray-300">
            Statut actuel : <span className="font-semibold text-white">{user.mfa_enabled ? "Activé" : "Désactivé"}</span>
          </p>
        </div>

        {user.mfa_enabled ? (
          <div className="mt-6 grid gap-4 sm:grid-cols-[1fr_auto]">
            <div className="space-y-3">
              <p className="text-sm text-gray-300">Pour désactiver le MFA, entrez votre mot de passe et le code de 6 chiffres actuel.</p>
              <label className="block text-[11px] uppercase tracking-[0.18em] text-gray-400">Mot de passe</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-xl border border-red-800 bg-[#090909] px-4 py-3 text-sm text-white outline-none"
                autoComplete="current-password"
              />
              <label className="block text-[11px] uppercase tracking-[0.18em] text-gray-400">Code MFA</label>
              <input
                type="text"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                className="w-full rounded-xl border border-red-800 bg-[#090909] px-4 py-3 text-sm text-white outline-none"
                inputMode="numeric"
                placeholder="000000"
              />
            </div>
            <button
              type="button"
              disabled={isSubmitting}
              onClick={handleDisable}
              className="rounded-2xl bg-red-700 px-6 py-4 text-sm font-semibold uppercase tracking-[0.12em] text-white transition hover:bg-red-600 disabled:opacity-50"
            >
              Désactiver
            </button>
          </div>
        ) : (
          <div className="mt-6 grid gap-4">
            <button
              type="button"
              disabled={isSubmitting}
              onClick={handleMfaSetup}
              className="rounded-2xl bg-red-700 px-6 py-4 text-sm font-semibold uppercase tracking-[0.12em] text-white transition hover:bg-red-600 disabled:opacity-50"
            >
              Générer la configuration MFA
            </button>

            {setupData ? (
              <div className="grid gap-4 rounded-3xl border border-red-800 bg-[#070707]/90 p-5">
                <div className="flex flex-col gap-2">
                  <p className="text-sm text-gray-300">Scannez ce QR code avec votre application d&apos;authentification :</p>
                  {qrUrl ? (
                    <img src={qrUrl} alt="QR code MFA" className="h-52 w-52 rounded-2xl bg-white/5 p-2" />
                  ) : null}
                  <p className="text-xs text-gray-500 break-all">Secret : {setupData.secret}</p>
                </div>

                <div className="space-y-3">
                  <label className="block text-[11px] uppercase tracking-[0.18em] text-gray-400">Code de vérification</label>
                  <input
                    type="text"
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                    className="w-full rounded-xl border border-red-800 bg-[#090909] px-4 py-3 text-sm text-white outline-none"
                    inputMode="numeric"
                    placeholder="000000"
                  />
                  <button
                    type="button"
                    disabled={isSubmitting}
                    onClick={handleEnable}
                    className="w-full rounded-2xl bg-red-700 px-6 py-4 text-sm font-semibold uppercase tracking-[0.12em] text-white transition hover:bg-red-600 disabled:opacity-50"
                  >
                    Activer MFA
                  </button>
                </div>
              </div>
            ) : (
              <p className="text-sm text-gray-400">Vous pouvez activer le MFA pour ajouter une couche de sécurité à votre compte.</p>
            )}
          </div>
        )}

        {status ? (
          <div className="mt-6 rounded-2xl border border-red-800 bg-[#110000] px-4 py-3 text-sm text-red-200">
            {status}
          </div>
        ) : null}
      </section>
    </div>
  );
}
