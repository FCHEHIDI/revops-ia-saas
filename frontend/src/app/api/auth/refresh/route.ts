import { type NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

/**
 * Proxies the refresh request to the backend.
 * The browser sends its httpOnly refresh_token cookie automatically.
 * The backend rotates both cookies and returns a success message.
 */
export async function POST(request: NextRequest) {
  try {
    const cookieHeader = request.headers.get("cookie") ?? "";

    const backendRes = await fetch(`${BACKEND_URL}/auth/refresh`, {
      method: "POST",
      headers: {
        cookie: cookieHeader,
        "Content-Type": "application/json",
      },
    });

    const data = (await backendRes.json()) as unknown;

    // Forward Set-Cookie headers from backend to client
    const response = NextResponse.json(data, { status: backendRes.status });
    const setCookies = backendRes.headers.getSetCookie?.() ?? [];
    setCookies.forEach((cookie) => {
      response.headers.append("Set-Cookie", cookie);
    });

    return response;
  } catch (err) {
    console.error("[auth/refresh] error:", err);
    return NextResponse.json({ error: "Refresh failed" }, { status: 500 });
  }
}
