"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { authApi } from "@/lib/api";
import type { User, LoginRequest } from "@/types";

interface AuthState {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
}

interface UseAuthReturn extends AuthState {
  login: (data: LoginRequest) => Promise<void>;
  logout: () => Promise<void>;
  refetch: () => Promise<void>;
}

export function useAuth(): UseAuthReturn {
  const router = useRouter();
  const [state, setState] = useState<AuthState>({
    user: null,
    isLoading: true,
    isAuthenticated: false,
  });

  const fetchUser = useCallback(async () => {
    try {
      const user = await authApi.me();
      setState({ user, isLoading: false, isAuthenticated: true });
    } catch {
      setState({ user: null, isLoading: false, isAuthenticated: false });
    }
  }, []);

  useEffect(() => {
    fetchUser();
  }, [fetchUser]);

  const login = useCallback(
    async (data: LoginRequest) => {
      await authApi.login(data);
      // Backend sets httpOnly cookies on successful login
      // Fetch user info after login
      const user = await authApi.me();
      setState({ user, isLoading: false, isAuthenticated: true });
      router.push("/chat");
    },
    [router]
  );

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      setState({ user: null, isLoading: false, isAuthenticated: false });
      router.push("/login");
    }
  }, [router]);

  return {
    ...state,
    login,
    logout,
    refetch: fetchUser,
  };
}
