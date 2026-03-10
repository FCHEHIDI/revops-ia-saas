"use client";

import { LogOut, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/useAuth";

interface HeaderProps {
  title?: string;
}

export function Header({ title }: HeaderProps) {
  const { user, logout } = useAuth();

  return (
    <header className="flex items-center justify-between border-b border-slate-700 bg-slate-900 px-6 py-3">
      {title && (
        <h1 className="text-lg font-semibold text-slate-100">{title}</h1>
      )}
      {!title && <div />}

      <div className="flex items-center gap-3">
        {user && (
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-full bg-indigo-500/20">
              <User className="h-4 w-4 text-indigo-400" />
            </div>
            <span className="hidden text-sm text-slate-300 sm:block">
              {user.full_name || user.email}
            </span>
          </div>
        )}
        <Button
          variant="ghost"
          size="sm"
          onClick={logout}
          className="gap-1.5 text-slate-400 hover:text-red-400"
          aria-label="Se déconnecter"
        >
          <LogOut size={15} />
          <span className="hidden sm:inline">Déconnexion</span>
        </Button>
      </div>
    </header>
  );
}
