"use client";

/**
 * AuthContext — single source of truth for authentication state.
 *
 * Replaces the previous pattern where every `useAuth()` call created its own
 * isolated state and fired an independent GET /auth/me request.
 *
 * Usage:
 *   // Wrap the tree once (already done in <Providers>):
 *   <AuthProvider>{children}</AuthProvider>
 *
 *   // Consume anywhere:
 *   const { user, isAuthenticated, login, logout } = useAuthContext();
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { useRouter } from "next/navigation";
import { authApi } from "@/lib/api";
import type { LoginRequest, User } from "@/types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface AuthState {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
}

export interface AuthContextValue extends AuthState {
  login: (data: LoginRequest) => Promise<void>;
  logout: () => Promise<void>;
  refetch: () => Promise<void>;
  hasRole: (role: string) => boolean;
  can: (permission: string) => boolean;
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

const AuthContext = createContext<AuthContextValue | null>(null);

// Key for the non-sensitive localStorage flag that indicates a session may
// exist.  Avoids firing GET /auth/me (and logging a 401) on every page load
// for unauthenticated visitors.  The flag carries no secret — the real auth
// check is still done via httpOnly cookies on the backend.
const AUTH_HINT_KEY = "auth_hint";

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();

  const [state, setState] = useState<AuthState>({
    user: null,
    isLoading: true,
    isAuthenticated: false,
  });

  const fetchUser = useCallback(async () => {
    // Skip the network call when there is no session hint so we don't log a
    // 401 for every unauthenticated page visit.
    if (typeof window !== "undefined" && !localStorage.getItem(AUTH_HINT_KEY)) {
      setState({ user: null, isLoading: false, isAuthenticated: false });
      return;
    }
    try {
      const user = await authApi.me();
      setState({ user, isLoading: false, isAuthenticated: true });
    } catch {
      // Session expired or revoked — clear the hint so the next load is silent.
      if (typeof window !== "undefined") {
        localStorage.removeItem(AUTH_HINT_KEY);
      }
      setState({ user: null, isLoading: false, isAuthenticated: false });
    }
  }, []);

  // Single /auth/me call for the entire tree.
  useEffect(() => {
    fetchUser();
  }, [fetchUser]);

  const login = useCallback(
    async (data: LoginRequest) => {
      await authApi.login(data);
      // Mark that a session now exists before fetching the user profile.
      if (typeof window !== "undefined") {
        localStorage.setItem(AUTH_HINT_KEY, "1");
      }
      // Backend sets httpOnly cookies on success — fetch user info immediately
      // so the shared state is populated before the route transition completes.
      const user = await authApi.me();
      setState({ user, isLoading: false, isAuthenticated: true });
      router.push("/chat");
    },
    [router],
  );

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      if (typeof window !== "undefined") {
        localStorage.removeItem(AUTH_HINT_KEY);
      }
      setState({ user: null, isLoading: false, isAuthenticated: false });
      router.push("/login");
    }
  }, [router]);

  const hasRole = useCallback(
    (role: string) => state.user?.roles?.includes(role) ?? false,
    [state.user],
  );

  const can = useCallback(
    (permission: string) =>
      state.user?.permissions?.includes(permission) ?? false,
    [state.user],
  );

  return (
    <AuthContext.Provider
      value={{ ...state, login, logout, refetch: fetchUser, hasRole, can }}
    >
      {children}
    </AuthContext.Provider>
  );
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useAuthContext(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuthContext must be used within <AuthProvider>");
  }
  return ctx;
}
