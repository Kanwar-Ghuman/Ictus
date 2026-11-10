// Calls to the trading bot, through this app's own /api/bot route.

export class BotError extends Error {
  constructor(message: string, readonly offline: boolean) {
    super(message);
  }
}

/** GET with no body, POST with one. Throws BotError with the bot's own message. */
export async function bot<T>(action: string, body?: unknown): Promise<T> {
  const post = body !== undefined;
  let response: Response;
  try {
    response = await fetch(`/api/bot/${action}`, {
      method: post ? "POST" : "GET",
      headers: post ? { "Content-Type": "application/json" } : undefined,
      body: post ? JSON.stringify(body) : undefined,
      cache: "no-store",
    });
  } catch {
    throw new BotError("Can't reach the dashboard server.", true);
  }
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data && typeof data === "object" && "detail" in data
      ? String(data.detail)
      : `Error ${response.status}`;
    throw new BotError(detail, response.status === 503);
  }
  return data as T;
}
