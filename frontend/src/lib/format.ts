// Numbers as the dashboard shows them. A missing value is a dash.

const MISSING = "—";

export function usd(value: string | number | null | undefined): string {
  const n = Number(value);
  if (value === null || value === undefined || !Number.isFinite(n)) return MISSING;
  return n.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

/** A gain or a loss with its sign: +$1.20, −$0.45. */
export function signedUsd(value: number): string {
  return `${value >= 0 ? "+" : "−"}${usd(Math.abs(value))}`;
}

export function cents(value: number | null): string {
  return value === null || !Number.isFinite(value) ? MISSING : `${Math.round(value * 100)}¢`;
}

export function pct(value: number | null): string {
  return value === null || !Number.isFinite(value) ? MISSING : `${Math.round(value * 100)}%`;
}

export function num(value: string | null | undefined): number | null {
  return value === null || value === undefined || value === "" ? null : Number(value);
}
