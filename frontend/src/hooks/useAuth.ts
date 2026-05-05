"use client";

/**
 * useAuth — thin proxy to the shared AuthContext.
 *
 * All call sites remain unchanged.  The actual state and the single
 * GET /auth/me request live in <AuthProvider> (mounted once in <Providers>).
 */

export { useAuthContext as useAuth } from "@/contexts/auth-context";
