"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  MessageSquare,
  Users,
  CreditCard,
  BarChart2,
  Mail,
  FileText,
  LayoutDashboard,
} from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/chat",      label: "Xenito",      icon: MessageSquare, section: "IA" },
  { href: "/dashboard", label: "Dashboard",  icon: LayoutDashboard, section: "CRM" },
  { href: "/crm",       label: "CRM",        icon: Users,         section: "CRM" },
  { href: "/analytics", label: "Analytics",  icon: BarChart2,     section: "CRM" },
  { href: "/billing",   label: "Facturation",icon: CreditCard,    section: "OPS" },
  { href: "/sequences", label: "Séquences",  icon: Mail,          section: "OPS" },
  { href: "/documents", label: "Documents",  icon: FileText,      section: "OPS" },
];

const sections = ["IA", "CRM", "OPS"] as const;

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside
      className="flex h-full flex-col overflow-y-auto overflow-x-hidden"
      style={{
        width: "260px",
        flexShrink: 0,
        background: "linear-gradient(180deg, #0d001a 0%, #0a0012 40%, #070010 100%)",
        borderRight: "1px solid rgba(255,0,0,0.1)",
        boxShadow: "2px 0 32px rgba(255,0,0,0.04)",
      }}
    >
      {/* ── Logo ── */}
      <div
        className="flex items-center gap-3 px-4 py-5"
        style={{ borderBottom: "1px solid rgba(255,255,255,0.05)" }}
      >
        <div
          className="flex h-12 w-12 items-center justify-center overflow-hidden rounded-xl flex-shrink-0"
          style={{ background: "rgba(255,0,0,0.08)", border: "1px solid rgba(255,0,0,0.2)" }}
        >
          <Image
            src="/favicon.png"
            alt="ROI"
            width={40}
            height={40}
            className="object-contain"
            priority
          />
        </div>
        <div>
          <div
            className="font-orbitron text-sm font-black tracking-widest"
            style={{ color: "#f5f5f5" }}
          >
            ROI
          </div>
          <div className="text-xs" style={{ color: "#555", letterSpacing: "0.05em" }}>
            RevOps Intelligence
          </div>
        </div>
      </div>

      {/* ── Navigation ── */}
      <nav className="flex-1 px-3 py-4 space-y-5">
        {sections.map((section) => {
          const items = navItems.filter((i) => i.section === section);
          return (
            <div key={section}>
              <div
                className="px-3 mb-1.5 text-xs font-semibold tracking-widest uppercase"
                style={{ color: "#333" }}
              >
                {section}
              </div>
              <div className="space-y-0.5">
                {items.map(({ href, label, icon: Icon }) => {
                  const isActive = pathname === href || pathname.startsWith(href + "/");
                  return (
                    <Link
                      key={href}
                      href={href}
                      className={cn(
                        "relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-200",
                        isActive
                          ? "text-white"
                          : "hover:text-white"
                      )}
                      style={
                        isActive
                          ? {
                              background: "rgba(255,0,0,0.07)",
                              border: "1px solid rgba(255,0,0,0.18)",
                              boxShadow: "inset 0 0 20px rgba(255,0,0,0.04)",
                              color: "#f5f5f5",
                            }
                          : {
                              background: "transparent",
                              border: "1px solid transparent",
                              color: "#555",
                            }
                      }
                    >
                      {/* Active indicator bar */}
                      {isActive && (
                        <span
                          className="absolute left-[-12px] top-1/2 -translate-y-1/2 w-0.5 h-6 rounded-r"
                          style={{
                            background: "#ff0000",
                            boxShadow: "0 0 16px rgba(255,0,0,0.95), 0 0 36px rgba(255,0,0,0.45)",
                          }}
                        />
                      )}
                      {href === "/chat" ? (
                        <div
                          className="flex h-4 w-4 shrink-0 items-center justify-center overflow-hidden rounded"
                          style={{
                            boxShadow: isActive ? "0 0 8px rgba(255,0,0,0.5)" : "none",
                            transition: "box-shadow 0.2s",
                          }}
                        >
                          <Image
                            src="/xenito.png"
                            alt="Xenito"
                            width={16}
                            height={16}
                            className="object-contain"
                          />
                        </div>
                      ) : (
                        <Icon
                          size={16}
                          className="shrink-0"
                          style={{ color: isActive ? "#ff0000" : "#444" }}
                        />
                      )}
                      {label}
                    </Link>
                  );
                })}
              </div>
            </div>
          );
        })}
      </nav>

      {/* ── Footer ── */}
      <div
        className="px-4 py-3"
        style={{ borderTop: "1px solid rgba(255,255,255,0.04)" }}
      >
        <p className="text-xs" style={{ color: "#333" }}>
          v0.1.0 · ROI SaaS
        </p>
      </div>
    </aside>
  );
}
