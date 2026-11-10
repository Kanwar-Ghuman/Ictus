"use client";

import { useState } from "react";

import { PageHero } from "@/components/PageHero";

/** Shown when the bot is not running: the one command that starts it. */
export function BotOffline() {
  return (
    <PageHero>
      <div className="hero-copy">
        <h1 className="hero-title">
          <span className="hero-strong">The bot isn&apos;t running</span>
          <span className="hero-mute">
            Start everything with one command from the project folder, then this page connects on its own.
          </span>
        </h1>
        <Command label="Practice (no money)" command="./ictus.sh" />
        <Command label="Real money, at most $20 on the event" command="./ictus.sh live 20" />
        <p className="fine">
          The bot trades before and during fights. Press Ctrl+C in that terminal to stop everything.
        </p>
      </div>
    </PageHero>
  );
}

function Command({ label, command }: { label: string; command: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => void navigator.clipboard.writeText(command).then(() => setCopied(true));
  return (
    <div>
      <p className="cmd-label">{label}</p>
      <div className="cmd">
        <span className="break-all">{command}</span>
        <button type="button" onClick={copy}>{copied ? "Copied" : "Copy"}</button>
      </div>
    </div>
  );
}
