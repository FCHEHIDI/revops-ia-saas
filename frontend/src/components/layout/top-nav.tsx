"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useRef, useEffect } from "react";
import { Search, LogOut } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/hooks/useAuth";
import { NotificationPanel } from "@/components/notifications/notification-panel";

const navItems = [
  { href: "/chat",      label: "Xenito"      },
  { href: "/dashboard", label: "Dashboard"   },
  { href: "/crm",       label: "CRM"         },
  { href: "/analytics", label: "Analytics"   },
  { href: "/billing",   label: "Facturation" },
  { href: "/sequences", label: "Séquences"   },
  { href: "/documents", label: "Documents"   },
];

/* ── Compact user menu with logout dropdown ─────────────── */
function UserMenu({ user, logout }: { user: { full_name: string; email: string }; logout: () => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const initials = user.full_name
    .split(" ")
    .slice(0, 2)
    .map((n) => n[0])
    .join("")
    .toUpperCase();

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button
        onClick={() => setOpen(!open)}
        title={user.full_name}
        style={{
          width: 32,
          height: 32,
          borderRadius: "50%",
          background: "radial-gradient(circle at 38% 32%, #3A0000, #0A0000)",
          border: `1.5px solid ${open ? "var(--red-doge)" : "var(--red-dark)"}`,
          color: "var(--red-doge)",
          fontSize: 11,
          fontWeight: 700,
          fontFamily: "var(--font-title)",
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          transition: "border-color 0.15s, box-shadow 0.15s",
          boxShadow: open ? "var(--glow-red)" : "none",
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.borderColor = "var(--red-doge)";
          e.currentTarget.style.boxShadow = "var(--glow-red)";
        }}
        onMouseLeave={(e) => {
          if (!open) {
            e.currentTarget.style.borderColor = "var(--red-dark)";
            e.currentTarget.style.boxShadow = "none";
          }
        }}
      >
        {initials}
      </button>

      {open && (
        <div
          style={{
            position: "absolute",
            top: "calc(100% + 8px)",
            right: 0,
            minWidth: 200,
            background: "var(--bg-surface)",
            border: "1px solid var(--border-default)",
            borderRadius: 10,
            boxShadow: "var(--shadow-deep)",
            zIndex: 100,
            overflow: "hidden",
          }}
        >
          {/* User info */}
          <div style={{ padding: "12px 14px 10px", borderBottom: "1px solid var(--border-subtle)" }}>
            <p style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", lineHeight: 1.3 }}>
              {user.full_name}
            </p>
            <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>{user.email}</p>
          </div>

          {/* Logout */}
          <button
            onClick={() => { setOpen(false); logout(); }}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              width: "100%",
              padding: "9px 14px",
              background: "transparent",
              border: "none",
              cursor: "pointer",
              color: "var(--text-secondary)",
              fontSize: 13,
              textAlign: "left",
              transition: "background 0.15s, color 0.15s",
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = "rgba(192,0,0,0.08)";
              e.currentTarget.style.color = "var(--red-glow)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = "transparent";
              e.currentTarget.style.color = "var(--text-secondary)";
            }}
          >
            <LogOut size={13} />
            Se déconnecter
          </button>
        </div>
      )}
    </div>
  );
}

/* ── TopNav ─────────────────────────────────────────────── */
export function TopNav() {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const [hoveredNav, setHoveredNav] = useState<string | null>(null);

  return (
    <header
      className={cn("flex items-center w-full shrink-0 px-5 gap-4")}
      style={{
        height: "56px",
        position: "relative",
        zIndex: 50,
        background: "rgba(5,5,5,0.90)",
        backdropFilter: "blur(16px)",
        WebkitBackdropFilter: "blur(16px)",
        borderBottom: "1px solid var(--red-dark)",
        boxShadow: "0 1px 0 rgba(138,0,0,0.15)",
      }}
    >
      {/* ── Logo → /dashboard ── */}
      <Link
        href="/dashboard"
        className="flex items-center gap-2 shrink-0"
        style={{ textDecoration: "none" }}
      >
        <Image
          src="/favicon.png"
          alt="RevOps IA"
          width={28}
          height={28}
          className="object-contain"
          priority
        />
        <div className="hidden sm:flex flex-col leading-none gap-0.5">
          <span
            className="font-cinzel text-xs font-bold tracking-[0.18em] uppercase"
            style={{ color: "var(--white-spectral)" }}
          >
            RevOps
          </span>
          <span
            style={{
              fontSize: "0.6rem",
              letterSpacing: "0.12em",
              color: "var(--red-doge)",
              fontFamily: "var(--font-body)",
            }}
          >
            Intelligence
          </span>
        </div>
      </Link>

      {/* ── Separator ── */}
      <div style={{ width: 1, height: 28, background: "var(--border-default)", flexShrink: 0 }} />

      {/* ── Nav items — texte Cinzel ── */}
      <nav className="flex items-center flex-1" style={{ gap: 2 }}>
        {navItems.map(({ href, label }) => {
          const isActive = pathname === href || pathname.startsWith(href + "/");
          const isHovered = hoveredNav === href;

          return (
            <Link
              key={href}
              href={href}
              onMouseEnter={() => setHoveredNav(href)}
              onMouseLeave={() => setHoveredNav(null)}
              className="relative shrink-0"
              style={{
                display: "inline-flex",
                alignItems: "center",
                height: 44,
                padding: "0 12px",
                textDecoration: "none",
                fontFamily: "var(--font-title)",
                fontSize: 11,
                fontWeight: isActive ? 700 : 400,
                letterSpacing: "0.12em",
                textTransform: "uppercase",
                color: isActive
                  ? "var(--white-spectral)"
                  : isHovered
                  ? "var(--gray-silver)"
                  : "var(--text-muted)",
                transition: "color 0.15s",
                borderBottom: isActive
                  ? "2px solid var(--red-doge)"
                  : "2px solid transparent",
                marginBottom: -1,
              }}
            >
              {label}
            </Link>
          );
        })}
      </nav>

      {/* ── Right side: search + notifications + user ── */}
      <div className="flex items-center gap-2 ml-auto shrink-0">
        {/* Ctrl+K search */}
        <button
          onClick={() => window.dispatchEvent(new CustomEvent("cmdpalette:open"))}
          aria-label="Recherche globale (Ctrl+K)"
          title="Ctrl+K"
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            height: 28,
            padding: "0 10px",
            borderRadius: 6,
            background: "rgba(255,255,255,0.03)",
            border: "1px solid rgba(255,255,255,0.07)",
            cursor: "pointer",
            transition: "background 0.15s, border-color 0.15s",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = "rgba(255,255,255,0.06)";
            e.currentTarget.style.borderColor = "rgba(255,255,255,0.12)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = "rgba(255,255,255,0.03)";
            e.currentTarget.style.borderColor = "rgba(255,255,255,0.07)";
          }}
        >
          <Search size={12} color="#666" />
          <span style={{ fontSize: 11, color: "#555", whiteSpace: "nowrap" }}>Chercher</span>
          <kbd
            style={{
              fontSize: 9,
              color: "#444",
              background: "rgba(255,255,255,0.04)",
              border: "1px solid rgba(255,255,255,0.07)",
              borderRadius: 3,
              padding: "1px 4px",
            }}
          >
            Ctrl K
          </kbd>
        </button>

        <NotificationPanel />
        {user && <UserMenu user={user} logout={logout} />}
      </div>
    </header>
  );
}
