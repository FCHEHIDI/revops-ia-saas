import { type NextRequest, NextResponse } from "next/server";

const PROTECTED_PATHS = ["/chat", "/crm", "/billing", "/analytics", "/sequences", "/documents"];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  const isProtected = PROTECTED_PATHS.some((p) => pathname.startsWith(p));
  if (!isProtected) return NextResponse.next();

  // The backend sets an httpOnly cookie named "access_token".
  // The Edge middleware can read request cookies to check presence.
  const hasToken = request.cookies.has("access_token");

  if (!hasToken) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("redirect", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/chat/:path*",
    "/crm/:path*",
    "/billing/:path*",
    "/analytics/:path*",
    "/sequences/:path*",
    "/documents/:path*",
  ],
};
