import { type NextRequest, NextResponse } from "next/server";
import type { ProcessRequest } from "@/types";

const ORCHESTRATOR_URL = process.env.NEXT_PUBLIC_ORCHESTRATOR_URL ?? "http://localhost:8001";
const INTERNAL_API_KEY = process.env.INTERNAL_API_KEY ?? "dev-secret-key";

export async function POST(request: NextRequest) {
  let body: ProcessRequest;
  try {
    body = (await request.json()) as ProcessRequest;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  if (!body.tenant_id || !body.message || !body.user_id || !body.conversation_id) {
    return NextResponse.json({ error: "Missing required fields" }, { status: 400 });
  }

  try {
    const upstreamRes = await fetch(`${ORCHESTRATOR_URL}/process`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Internal-API-Key": INTERNAL_API_KEY,
      },
      body: JSON.stringify(body),
    });

    if (!upstreamRes.ok || !upstreamRes.body) {
      return NextResponse.json(
        { error: `Orchestrator error: ${upstreamRes.status}` },
        { status: upstreamRes.status }
      );
    }

    // Stream the SSE response through to the client
    return new Response(upstreamRes.body, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
        "X-Accel-Buffering": "no",
      },
    });
  } catch (err) {
    console.error("[chat/stream] upstream error:", err);
    return NextResponse.json({ error: "Failed to reach orchestrator" }, { status: 502 });
  }
}
