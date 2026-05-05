import type { NextConfig } from "next";

const RAW_BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://127.0.0.1:18000/api/v1";

const BACKEND_URL = RAW_BACKEND_URL.replace("localhost", "127.0.0.1");

// Strip trailing /api/v1 if present so the rewrite destination is the root
const backendBase = BACKEND_URL.replace(/\/api\/v1\/?$/, "");

const nextConfig: NextConfig = {
  output: "standalone",

  // Proxy all /api/v1/* calls through the Next.js server so the browser
  // never makes cross-origin requests — CORS is structurally impossible.
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${backendBase}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
