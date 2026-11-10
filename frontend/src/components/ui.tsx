// Small pieces every part of the dashboard shares.

import type { ReactNode } from "react";

export type PillTone = "neutral" | "good" | "bad" | "muted";

const PILL_TONES: Record<PillTone, string> = {
  neutral: "pill-neutral",
  good: "pill-good",
  bad: "pill-bad",
  muted: "pill-muted",
};

export function Pill({ children, tone = "neutral" }: { children: ReactNode; tone?: PillTone }) {
  return <span className={`pill ${PILL_TONES[tone]}`}>{children}</span>;
}

export function Banner({ title, children, action }: {
  title: string; children: ReactNode; action?: ReactNode;
}) {
  return (
    <div className="banner site-width">
      <div>
        <p className="banner-title">{title}</p>
        <p className="banner-copy">{children}</p>
      </div>
      {action}
    </div>
  );
}

export function Figure({ label, value, tone }: { label: string; value: string; tone?: "good" | "bad" }) {
  const color = tone === "good" ? "text-hit" : tone === "bad" ? "text-blood" : "";
  return (
    <div>
      <dt className="figure-label">{label}</dt>
      <dd className={`figure-value ${color}`}>{value}</dd>
    </div>
  );
}
