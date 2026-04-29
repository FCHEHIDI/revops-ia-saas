"use client";

import { LogOut, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/useAuth";

interface HeaderProps {
  title?: string;
  eyebrow?: string;
}

export function Header({ title, eyebrow }: HeaderProps) {
  const { user, logout } = useAuth();

  return (
    <header
      className="flex items-center justify-between px-6 py-3 flex-shrink-0"
      style={{
        background: "var(--bg-base)",
        borderBottom: "1px solid var(--border-subtle)",
      }}
    >
      <div>
        {eyebrow && (
          <p
            className="text-xs font-semibold tracking-widest uppercase mb-0.5 text-glow-blue"
            style={{ color: "var(--accent-blue)" }}
          >
            {eyebrow}
          </p>
        )}
        {title && (
          <h1 className="text-lg font-semibold" style={{ color: "var(--text-primary)" }}>
            {title}
          </h1>
        )}
        {!title && !eyebrow && <div />}
      </div>

      <div className="flex items-center gap-3">
        {user && (
          <div className="flex items-center gap-2">
            <div
              className="flex h-7 w-7 items-center justify-center rounded-full"
              style={{ background: "rgba(255,0,0,0.1)", border: "1px solid rgba(255,0,0,0.25)" }}
            >
              <User size={14} style={{ color: "var(--accent-red)" }} />
            </div>
            <span className="hidden text-sm sm:block" style={{ color: "var(--text-secondary)" }}>
              {user.full_name || user.email}
            </span>
          </div>
        )}
        <button
          onClick={logout}
          className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm transition-all duration-200 hover:text-white"
          style={{
            color: "var(--text-muted)",
            border: "1px solid transparent",
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLButtonElement).style.border = "1px solid rgba(255,0,0,0.3)";
            (e.currentTarget as HTMLButtonElement).style.background = "rgba(255,0,0,0.06)";
            (e.currentTarget as HTMLButtonElement).style.color = "var(--accent-red)";
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLButtonElement).style.border = "1px solid transparent";
            (e.currentTarget as HTMLButtonElement).style.background = "transparent";
            (e.currentTarget as HTMLButtonElement).style.color = "var(--text-muted)";
          }}
          aria-label="Se déconnecter"
        >
          <LogOut size={14} />
          <span className="hidden sm:inline">Déconnexion</span>
        </button>
      </div>
    </header>
  );
}
