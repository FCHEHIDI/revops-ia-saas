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
  { href: "/chat",      label: "Xenito",      customIcon: "/icons/xenito-icon.png"      },
  { href: "/dashboard", label: "Dashboard",   customIcon: "/icons/dashboard-icon.png"   },
  { href: "/crm",       label: "CRM",         customIcon: "/icons/crm-icon.png"         },
  { href: "/analytics", label: "Analytics",   customIcon: "/icons/analytics-icon.png"   },
  { href: "/billing",   label: "Facturation", customIcon: "/icons/facturation-icon.png" },
  { href: "/sequences", label: "Séquences",   customIcon: "/icons/sequences-icon.png"   },
  { href: "/documents", label: "Documents",   customIcon: "/icons/documents-icon.png"   },
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

      {/* ── Nav items ── */}
      <nav className="flex items-center gap-0.5 flex-1">
        {navItems.map(({ href, label, customIcon }) => {
          const isActive = pathname === href || pathname.startsWith(href + "/");
          const isHovered = hoveredNav === href;

          return (
            <Link
              key={href}
              href={href}
              title={label}
              onMouseEnter={() => setHoveredNav(href)}
              onMouseLeave={() => setHoveredNav(null)}
              className="relative flex flex-col items-center justify-center shrink-0 rounded-lg transition-all duration-200"
              style={{
                padding: "4px 8px",
                gap: 2,
                background: isActive
                  ? "rgba(138,0,0,0.15)"
                  : isHovered
                  ? "rgba(138,0,0,0.07)"
                  : "transparent",
                border: isActive
                  ? "1px solid var(--red-dark)"
                  : "1px solid transparent",
                boxShadow: isActive ? "inset 0 0 10px rgba(138,0,0,0.25)" : "none",
                textDecoration: "none",
                minWidth: 52,
              }}
            >
              <div
                style={{
                  filter: isActive
                    ? "drop-shadow(0 0 5px rgba(255,0,0,0.6))"
                    : isHovered
                    ? "brightness(1.2)"
                    : "grayscale(0.1) opacity(0.65)",
                  transition: "filter 0.2s",
                  height: 24,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <Image
                  src={customIcon}
                  alt={label}
                  width={24}
                  height={24}
                  style={{ width: 24, height: 24, objectFit: "contain" }}
                />
              </div>
              <span
                style={{
                  fontSize: 9,
                  fontFamily: "var(--font-body)",
                  color: isActive ? "var(--red-doge)" : "var(--text-muted)",
                  letterSpacing: "0.04em",
                  whiteSpace: "nowrap",
                  transition: "color 0.2s",
                  lineHeight: 1,
                }}
              >
                {label}
              </span>
              {/* Active underline bar */}
              {isActive && (
                <span
                  className="absolute bottom-[-4px] left-1/2 -translate-x-1/2 rounded-full"
                  style={{
                    width: "60%",
                    height: 2,
                    background: "var(--red-doge)",
                    boxShadow: "0 0 8px rgba(192,0,0,0.8)",
                  }}
                />
              )}
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