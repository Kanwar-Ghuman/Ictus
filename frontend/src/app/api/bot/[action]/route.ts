import { readFile } from "node:fs/promises";
import path from "node:path";

// Server-side bridge to the local trading service. The dashboard token is read
// here from model/.env and never reaches the browser. Only same-origin requests
// to a loopback host are forwarded, and only these actions.
const BOT = process.env.TRADING_API_BASE || "http://127.0.0.1:8002";
const ALLOWED: Record<string, Set<string>> = {
  GET: new Set(["status", "plan", "prepare"]),
  POST: new Set(["quickstart", "stop", "reconcile", "prepare"]),
};
const LOOPBACK = new Set(["localhost", "127.0.0.1", "[::1]"]);

export const dynamic = "force-dynamic";

async function dashboardToken(): Promise<string | null> {
  if (process.env.ICTUS_TRADING_TOKEN) return process.env.ICTUS_TRADING_TOKEN;
  const envFile = process.env.ICTUS_ENV_FILE || path.join(/*turbopackIgnore: true*/ process.cwd(), "..", "model", ".env");
  try {
    const text = await readFile(/*turbopackIgnore: true*/ envFile, "utf8");
    const line = text.split(/\r?\n/).find((row) => row.startsWith("ICTUS_TRADING_TOKEN="));
    const value = line?.slice("ICTUS_TRADING_TOKEN=".length).trim().replace(/^["']|["']$/g, "");
    return value || null;
  } catch {
    return null;
  }
}

function fromThisApp(request: Request): boolean {
  const host = request.headers.get("host") ?? "";
  if (!LOOPBACK.has(host.replace(/:\d+$/, ""))) return false; // also blocks DNS rebinding
  const site = request.headers.get("sec-fetch-site");
  if (site && site !== "same-origin" && site !== "none") return false;
  if (request.method !== "GET") {
    const origin = request.headers.get("origin");
    try {
      if (!origin || new URL(origin).host !== host) return false;
    } catch {
      return false;
    }
  }
  return true;
}

function reply(status: number, detail: string) {
  return Response.json({ detail }, { status, headers: { "Cache-Control": "no-store" } });
}

async function forward(request: Request, action: string) {
  if (!ALLOWED[request.method]?.has(action)) return reply(404, "Unknown action");
  if (!fromThisApp(request)) return reply(403, "Bot controls are available from this computer only");
  const token = await dashboardToken();
  if (!token) return reply(500, "ICTUS_TRADING_TOKEN is missing from model/.env");
  const body = request.method === "POST" ? await request.text() : undefined;
  if (body && body.length > 4096) return reply(413, "Request too large");
  try {
    const response = await fetch(`${BOT}/api/trading/${action}`, {
      method: request.method,
      headers: { Authorization: `Bearer ${token}`, ...(body ? { "Content-Type": "application/json" } : {}) },
      body: body || undefined,
      cache: "no-store",
      signal: AbortSignal.timeout(action === "quickstart" ? 60_000 : 15_000),
    });
    return new Response(await response.text(), {
      status: response.status,
      headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
    });
  } catch {
    return reply(503, "The trading bot isn't running");
  }
}

type Context = { params: Promise<{ action: string }> };

export async function GET(request: Request, { params }: Context) {
  return forward(request, (await params).action);
}

export async function POST(request: Request, { params }: Context) {
  return forward(request, (await params).action);
}
