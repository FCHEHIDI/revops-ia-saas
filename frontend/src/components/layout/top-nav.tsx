"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { Search } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/hooks/useAuth";
import { ProfileCard } from "@/components/layout/profile-card";
import { NotificationPanel } from "@/components/notifications/notification-panel";

const navItems = [
  { href: "/chat",      label: "Xenito",      section: "IA",  customIcon: "/icons/xenito-icon.png"     },
  { href: "/dashboard", label: "Dashboard",   section: "CRM", customIcon: "/icons/dashboard-icon.png"  },
  { href: "/crm",       label: "CRM",         section: "CRM", customIcon: "/icons/crm-icon.png"        },
  { href: "/analytics", label: "Analytics",   section: "CRM", customIcon: "/icons/analytics-icon.png"  },
  { href: "/billing",   label: "Facturation", section: "OPS", customIcon: "/icons/facturation-icon.png" },
  { href: "/sequences", label: "Séquences",   section: "OPS", customIcon: "/icons/sequences-icon.png"  },
  { href: "/documents", label: "Documents",   section: "OPS", customIcon: "/icons/documents-icon.png"  },
];

export function TopNav() {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const [logoHover, setLogoHover] = useState(false);
  const [hoveredNav, setHoveredNav] = useState<string | null>(null);

  return (
    <header
      className="flex items-center w-full shrink-0 px-6 gap-3"
      style={{
        height: "170px",
        position: "relative",
        zIndex: 50,
        background: "rgba(5,5,5,0.75)",
        backdropFilter: "blur(16px)",
        WebkitBackdropFilter: "blur(16px)",
        borderBottom: "1px solid var(--red-dark)",
        boxShadow: "0 2px 32px rgba(0,0,0,0.8), 0 1px 0 rgba(138,0,0,0.2)",
      }}
    >
      {/* ── Logo → Logout ── */}
      <button
        onClick={logout}
        onMouseEnter={() => setLogoHover(true)}
        onMouseLeave={() => setLogoHover(false)}
        aria-label="Se déconnecter"
        className="flex items-center gap-2 shrink-0 mr-4"
        style={{
          background: "transparent",
          border: "none",
          cursor: "pointer",
          padding: 0,
          filter: logoHover ? "drop-shadow(0 0 14px rgba(255,0,0,0.75))" : "none",
          transition: "filter 0.25s",
        }}
      >
        <Image
          src="/favicon.png"
          alt="ROI"
          width={60}
          height={60}
          className="object-contain"
          priority
        />
        <div className="hidden sm:flex flex-col">
          <div
            className="font-cinzel text-sm font-bold tracking-[0.18em] uppercase"
            style={{
              color: logoHover ? "#ffffff" : "var(--white-spectral)",
              textShadow: logoHover ? "0 0 14px rgba(192,0,0,0.8)" : "none",
              transition: "color 0.2s, text-shadow 0.2s",
            }}
          >
            RevOps
          </div>
          <div
            className="text-xs"
            style={{
              color: logoHover ? "var(--red-doge)" : "var(--red-dark)",
              letterSpacing: "0.12em",
              fontSize: "0.65rem",
              transition: "color 0.2s",
              fontFamily: "var(--font-body)",
            }}
          >
            Intelligence
          </div>
          {/* "Déconnexion" visible seulement au hover */}
          <div
            style={{
              fontSize: "0.6rem",
              letterSpacing: "0.08em",
              color: "rgba(255,0,0,0.8)",
              marginTop: 2,
              opacity: logoHover ? 1 : 0,
              transform: logoHover ? "translateY(0)" : "translateY(-4px)",
              transition: "opacity 0.2s, transform 0.2s",
              pointerEvents: "none",
            }}
          >
            ↩ Déconnexion
          </div>
        </div>
      </button>

      {/* ── Nav items ── */}
      <nav className="flex items-center gap-4 flex-1">
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
              className={cn(
                "relative flex flex-col items-center justify-center shrink-0 rounded-xl transition-all duration-200"
              )}
              style={
                isActive
                  ? {
                      background: "rgba(138,0,0,0.15)",
                      border: "1px solid var(--red-dark)",
                      boxShadow: "var(--inner-shadow-red), var(--glow-red)",
                      padding: "4px 6px",
                    }
                  : {
                      background: isHovered ? "rgba(138,0,0,0.07)" : "transparent",
                      border: isHovered ? "1px solid rgba(138,0,0,0.3)" : "1px solid transparent",
                      padding: "4px 6px",
                    }
              }
            >
              {/* Active bottom bar */}
              {isActive && (
                <span
                  className="absolute bottom-[-5px] left-1/2 -translate-x-1/2 w-8 h-0.5 rounded-full"
                  style={{
                    background: "#ff0000",
                    boxShadow: "0 0 10px rgba(255,0,0,0.9), 0 0 24px rgba(255,0,0,0.4)",
                  }}
                />
              )}
              <div
                style={{
                  filter: isActive
                    ? "drop-shadow(0 0 8px rgba(255,0,0,0.65))"
                    : isHovered
                    ? "drop-shadow(0 0 6px rgba(255,255,255,0.25)) brightness(1.15)"
                    : "grayscale(0.1) opacity(0.65)",
                  transition: "filter 0.2s",
                }}
              >
                <Image
                  src={customIcon}
                  alt={label}
                  width={150}
                  height={150}
                  className="object-contain"
                />
              </div>
            </Link>
          );
        })}
      </nav>

      {/* ── Search button + Notification bell + Profile card ── */}
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginLeft: "auto" }}>
        {/* Cmd+K search trigger */}
        <button
          onClick={() => window.dispatchEvent(new CustomEvent("cmdpalette:open"))}
          aria-label="Recherche globale (Ctrl+K)"
          title="Ctrl+K"
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            height: 32,
            padding: "0 10px",
            borderRadius: 7,
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
          <Search size={13} color="#666" />
          <span style={{ fontSize: 12, color: "#555", whiteSpace: "nowrap" }}>
            Rechercher…
          </span>
          <kbd
            style={{
              fontSize: 9,
              color: "#444",
              background: "rgba(255,255,255,0.04)",
              border: "1px solid rgba(255,255,255,0.07)",
              borderRadius: 3,
              padding: "1px 4px",
              marginLeft: 4,
            }}
          >
            Ctrl K
          </kbd>
        </button>

        <NotificationPanel />
        {user && <ProfileCard user={user} />}
      </div>
    </header>
  );
}
