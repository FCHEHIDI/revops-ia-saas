/**
 * Auth helpers — the backend manages auth via httpOnly cookies (access_token + refresh_token).
 * The frontend never touches the tokens directly; it relies on:
 * - Cookie auto-send by the browser on every request (credentials: "include")
 * - GET /auth/me to verify session + get user info
 * - POST /auth/refresh to rotate tokens (called by the API client on 401)
 * - POST /auth/logout to clear cookies server-side
 */

// auth.ts is always server-side — use the absolute backend URL directly.
const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:18000/api/v1";

/**
 * Checks if the user is authenticated by calling /auth/me.
 * Returns true if the request succeeds (cookie is valid).
 */
export async function isAuthenticated(): Promise<boolean> {
  try {
    const res = await fetch(`${BACKEND_URL}/auth/me`, {
      credentials: "include",
      cache: "no-store",
    });
    return res.ok;
  } catch {
    return false;
  }
}

/**
 * Triggers token refresh — backend rotates both cookies.
 * Called automatically by the API client when a 401 is received.
 */
export async function refreshSession(): Promise<boolean> {
  try {
    const res = await fetch(`${BACKEND_URL}/auth/refresh`, {
      method: "POST",
      credentials: "include",
      cache: "no-store",
    });
    return res.ok;
  } catch {
    return false;
  }
}

/**
 * Logs out the user by calling /auth/logout.
 * The backend clears both httpOnly cookies.
 */
export async function serverLogout(): Promise<void> {
  await fetch(`${BACKEND_URL}/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
}
