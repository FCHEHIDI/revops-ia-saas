"use client";

import { useState } from "react";
import { Users, Building2, Activity, Tag } from "lucide-react";
import { ContactsTable } from "@/components/crm/contacts-table";

const NAV_ITEMS = [
  { id: "contacts",   label: "Contacts",   icon: Users },
  { id: "companies",  label: "Companies",  icon: Building2 },
  { id: "activities", label: "Activities", icon: Activity },
  { id: "segments",   label: "Segments",   icon: Tag },
];

export default function CrmPage() {
  const [activeTab, setActiveTab] = useState("contacts");

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <main className="flex-1 overflow-y-auto chat-scroll">

        {/* ── Hero — Salle des Masques ────────────────────────────── */}
        <div className="relative w-full overflow-hidden" style={{ height: 220 }}>
          <div
            className="absolute inset-0"
            style={{
              backgroundImage: "url('/visuels/crm.png')",
              backgroundSize: "cover",
              backgroundPosition: "center 40%",
              filter: "brightness(0.5) saturate(0.7)",
            }}
          />
          <div
            className="absolute inset-0"
            style={{
              background: "linear-gradient(to bottom, rgba(5,5,5,0.1) 0%, rgba(5,5,5,0.5) 60%, rgba(5,5,5,1) 100%)",
            }}
          />
          <div
            className="absolute inset-0 pointer-events-none"
            style={{
              background: "linear-gradient(90deg, rgba(138,0,0,0.2) 0%, transparent 12%, transparent 88%, rgba(138,0,0,0.2) 100%)",
            }}
          />
          <div className="absolute bottom-0 left-0 right-0 px-8 pb-6">
            <p
              className="font-cinzel text-xs tracking-[0.3em] uppercase mb-1"
              style={{ color: "var(--red-doge)" }}
            >
              Salle des Masques
            </p>
            <h1
              className="font-cinzel text-3xl font-bold"
              style={{ color: "var(--white-spectral)", textShadow: "0 0 32px rgba(192,0,0,0.4)" }}
            >
              CRM
            </h1>
            <p
              className="text-xs mt-1"
              style={{ color: "var(--gray-silver)", fontFamily: "var(--font-body)" }}
            >
              Registre des contacts &amp; deals
            </p>
          </div>
        </div>

        {/* ── Layout : sidebar + contenu ──────────────────────────── */}
        <div className="flex gap-6 px-8 py-8 items-start">

          {/* Sidebar nav */}
          <aside className="w-44 flex-shrink-0">
            <div className="tablette-marbre" style={{ padding: "10px 8px" }}>
              <p
                className="font-cinzel text-xs tracking-[0.2em] uppercase px-3 pb-2 mb-1"
                style={{ color: "var(--red-dark)", borderBottom: "1px solid rgba(138,0,0,0.2)" }}
              >
                Navigation
              </p>
              <div className="space-y-0.5 mt-2">
                {NAV_ITEMS.map((item) => {
                  const Icon = item.icon;
                  const isActive = activeTab === item.id;
                  return (
                    <button
                      key={item.id}
                      onClick={() => setActiveTab(item.id)}
                      className="w-full flex items-center gap-2.5 px-3 py-2 rounded transition-all duration-200 font-cinzel text-xs tracking-[0.08em]"
                      style={{
                        background: isActive ? "rgba(138,0,0,0.18)" : "transparent",
                        border: isActive ? "1px solid var(--red-dark)" : "1px solid transparent",
                        color: isActive ? "var(--red-doge)" : "var(--gray-silver)",
                        boxShadow: isActive ? "var(--inner-shadow-red)" : "none",
                        textAlign: "left",
                        cursor: "pointer",
                      }}
                      onMouseEnter={(e) => {
                        if (!isActive) {
                          e.currentTarget.style.background = "rgba(138,0,0,0.07)";
                          e.currentTarget.style.color = "var(--white-spectral)";
                        }
                      }}
                      onMouseLeave={(e) => {
                        if (!isActive) {
                          e.currentTarget.style.background = "transparent";
                          e.currentTarget.style.color = "var(--gray-silver)";
                        }
                      }}
                    >
                      <Icon size={12} />
                      {item.label}
                    </button>
                  );
                })}
              </div>
            </div>
          </aside>

          {/* Contenu principal */}
          <div className="flex-1 min-w-0">
            {activeTab === "contacts" && <ContactsTable />}
            {activeTab !== "contacts" && (
              <div className="tablette-marbre flex items-center justify-center" style={{ minHeight: 300 }}>
                <div className="text-center">
                  <p className="font-cinzel text-2xl mb-3" style={{ color: "var(--red-dark)" }}>⚜</p>
                  <p
                    className="font-cinzel text-xs tracking-[0.25em] uppercase"
                    style={{ color: "var(--gray-silver)" }}
                  >
                    Section en préparation
                  </p>
                </div>
              </div>
            )}
          </div>

        </div>
      </main>
    </div>
  );
}
