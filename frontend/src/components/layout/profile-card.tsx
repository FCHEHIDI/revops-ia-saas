"use client";

import { useRef, useState, useEffect, useCallback } from "react";
import { User, Camera, Briefcase, Copy, Check } from "lucide-react";
import { api } from "@/lib/api";
import type { User as UserType } from "@/types";

interface ProfileCardProps {
  user: UserType;
}

export function ProfileCard({ user }: ProfileCardProps) {
  const [avatar, setAvatar] = useState<string | null>(null);
  const [jobTitle, setJobTitle] = useState("");
  const [editingTitle, setEditingTitle] = useState(false);
  const [copied, setCopied] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    // Fallback rapide depuis localStorage, puis écrase avec la DB (multi-device)
    const cachedAvatar = localStorage.getItem("profile_avatar");
    if (cachedAvatar) setAvatar(cachedAvatar);
    const cachedTitle = localStorage.getItem("profile_job_title") || "";
    setJobTitle(cachedTitle);

    api.get<{ job_title?: string | null; avatar?: string | null }>("/users/me")
      .then((data) => {
        if (data.job_title != null) {
          setJobTitle(data.job_title);
          localStorage.setItem("profile_job_title", data.job_title);
        }
        if (data.avatar != null) {
          setAvatar(data.avatar);
          localStorage.setItem("profile_avatar", data.avatar);
        }
      })
      .catch(() => {});
  }, []);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async (ev) => {
      const dataUrl = ev.target?.result as string;
      setAvatar(dataUrl);
      localStorage.setItem("profile_avatar", dataUrl);
      try {
        await api.patch("/users/me", { avatar: dataUrl });
      } catch {
        // local cache already updated, API failure is non-blocking
      }
    };
    reader.readAsDataURL(file);
  };

  const saveTitle = useCallback(async () => {
    localStorage.setItem("profile_job_title", jobTitle);
    setEditingTitle(false);
    try {
      await api.patch("/users/me", { job_title: jobTitle });
    } catch {
      // local storage already saved, API failure is non-blocking
    }
  }, [jobTitle]);

  const copyEmail = useCallback(() => {
    navigator.clipboard.writeText(user.email).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [user.email]);

  return (
    <div className="flex items-center gap-3 shrink-0">
      {/* ── Avatar + bouton upload ── */}
      <div className="relative shrink-0">
        <div
          style={{
            width: 72,
            height: 72,
            borderRadius: "50%",
            overflow: "hidden",
            border: "2px solid rgba(255,0,0,0.3)",
            background: "rgba(255,0,0,0.08)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          {avatar ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={avatar}
              alt="avatar"
              style={{ width: "100%", height: "100%", objectFit: "cover" }}
            />
          ) : (
            <User size={32} style={{ color: "rgba(255,0,0,0.45)" }} />
          )}
        </div>
        <button
          onClick={() => fileRef.current?.click()}
          title="Changer la photo"
          style={{
            position: "absolute",
            bottom: 1,
            right: 1,
            width: 22,
            height: 22,
            borderRadius: "50%",
            background: "#ff0000",
            border: "2px solid #0a0012",
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Camera size={10} color="#fff" />
        </button>
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={handleFileChange}
        />
      </div>

      {/* ── Infos statiques ── */}
      <div className="flex flex-col gap-0.5 min-w-0">
        {/* Nom */}
        <p className="text-xs font-semibold truncate" style={{ color: "var(--text-primary)" }}>
          {user.full_name || "—"}
        </p>

        {/* Poste — éditable au clic */}
        <div className="flex items-center gap-1">
          <Briefcase size={10} style={{ color: "var(--text-muted)", flexShrink: 0 }} />
          {editingTitle ? (
            <input
              autoFocus
              value={jobTitle}
              onChange={(e) => setJobTitle(e.target.value)}
              onBlur={saveTitle}
              onKeyDown={(e) => e.key === "Enter" && saveTitle()}
              className="text-xs bg-transparent outline-none border-b"
              style={{
                color: "var(--text-secondary)",
                borderColor: "rgba(255,0,0,0.35)",
                width: 120,
              }}
              placeholder="Poste / titre"
            />
          ) : (
            <button
              onClick={() => setEditingTitle(true)}
              style={{
                font: "inherit",
                fontSize: "0.7rem",
                color: jobTitle ? "var(--text-secondary)" : "var(--text-muted)",
                cursor: "text",
                background: "transparent",
                border: "none",
                padding: 0,
                textAlign: "left",
              }}
              title="Cliquer pour modifier"
            >
              {jobTitle || "Ajouter un poste…"}
            </button>
          )}
        </div>

        {/* Email — clic pour copier */}
        <button
          onClick={copyEmail}
          className="flex items-center gap-1 min-w-0"
          style={{ background: "transparent", border: "none", padding: 0, cursor: "pointer" }}
          title="Copier l'adresse email"
        >
          {copied
            ? <Check size={10} style={{ color: "#22c55e", flexShrink: 0 }} />
            : <Copy size={10} style={{ color: "rgba(255,0,0,0.45)", flexShrink: 0 }} />}
          <span
            className="text-xs truncate"
            style={{ color: copied ? "#22c55e" : "rgba(255,0,0,0.55)", fontSize: "0.68rem", transition: "color 0.2s" }}
          >
            {copied ? "Copié !" : user.email}
          </span>
        </button>
      </div>
    </div>
  );
}
