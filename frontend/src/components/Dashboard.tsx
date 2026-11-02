"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type Decision = {
  ticker: string; bout: string; action: "skip" | "paper" | "demo" | "live"; reason: string;
  side?: string; probability?: number; p_f1?: number; price_dollars?: string; contracts?: number;
  cost_dollars?: string; edge?: number; phase?: string;
};
type Order = {
  id: string; bout_id: string; ticker: string; side: string; count: number; price_dollars: string;
  cost_dollars: string; reserved_dollars: string; status: string; filled_count: string;
};
type Status = {
  mode: "paper" | "demo" | "live"; running: boolean; feed_connected: boolean; market_connected: boolean;
  max_budget_dollars?: string | null; in_fight_enabled?: boolean; message: string;
  event: null | { budget_dollars: string; spent_dollars: string; reserved_dollars: string; remaining_dollars: string };
  decisions: Decision[]; orders: Order[];
  feed: null | { event_name: string; fights: Array<{ bout_id: string; status: string; fighter_a: string; fighter_b: string }> };
};
type PlanFight = {
  f1: string; f2: string; p_f1: number | null; bout_id: string | null; status: string | null;
  round: number | null; ticker: string | null; yes_fighter: string | null; yes_bid: string | null;
  yes_ask: string | null; rules_primary: string | null; rules_secondary: string | null;
  include: boolean; note: string; winner: string | null;
};
type Plan = {
  event: { name: string | null; status: string | null };
  card: null | { slug: string; event: string; date: string };
  fights: PlanFight[]; problem: string | null; needs_predictions?: boolean;
};
type Prepare = { state: "idle" | "running" | "done" | "failed" | "unavailable"; message: string };

class BotError extends Error {
  constructor(message: string, readonly offline: boolean) { super(message); }
}

async function bot<T>(action: string, body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/bot/${action}`, {
      method: body === undefined ? "GET" : "POST",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
    });
  } catch {
    throw new BotError("Can't reach the dashboard server.", true);
  }
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data && typeof data === "object" && "detail" in data ? String(data.detail) : `Error ${response.status}`;
    throw new BotError(detail, response.status === 503);
  }
  return data as T;
}

const usd = (value: string | number | null | undefined) => {
  const n = Number(value);
  return value === null || value === undefined || !Number.isFinite(n) ? "—"
    : n.toLocaleString("en-US", { style: "currency", currency: "USD" });
};
const cents = (value: number | null) => value === null || !Number.isFinite(value) ? "—" : `${Math.round(value * 100)}¢`;
const pct = (value: number | null) => value === null || !Number.isFinite(value) ? "—" : `${Math.round(value * 100)}%`;
const num = (value: string | null | undefined) => (value === null || value === undefined || value === "" ? null : Number(value));

const REASONS: Array<[RegExp, string | ((m: RegExpMatchArray) => string)]> = [
  [/^No edge: model (\d+)% on (.+?) vs (\d+)¢ all-in/,
    (m) => `Watching — model gives ${m[2]} ${m[1]}%, Kalshi wants ${m[3]}¢ (not cheap enough yet)`],
  [/budget share is used/i, "Bet placed — this fight's share of the budget is in"],
  [/Waiting \d+s before trying again/i, "Order didn't fully fill — trying again shortly"],
  [/Already tried \d+ times/i, "Done trying on this fight"],
  [/Spread \d+¢ too wide/i, "Waiting — Kalshi's buy/sell gap is too wide"],
  [/Not enough contracts offered/i, "Waiting — not enough contracts for sale"],
  [/started or (finished|unavailable)|observed started/i, "Fight started — no more pre-fight bets"],
  [/Live clock/i, "Fight is live — waiting for the round clock"],
  [/waiting for round totals/i, "Between rounds — letting the stats settle"],
  [/Too late in the break/i, "Missed this break"],
  [/Final round finished/i, "Last round done — waiting for the result"],
  [/fight feed disconnected|feed reports an error|ESPN source timestamp|Gateway timestamp/i, "Waiting for the fight feed"],
  [/websocket book|quote retrieval|Two-sided market/i, "Waiting for Kalshi prices"],
  [/Insufficient fighter history/i, "Skipped — not enough UFC history for the model"],
  [/Market is not open|closing|closed/i, "Kalshi market is closed"],
  [/Insufficient account cash/i, "Not enough cash in your Kalshi account"],
  [/budget exhausted/i, "Spending limit reached"],
];
const plain = (reason: string) => {
  for (const [pattern, text] of REASONS) {
    const match = reason.match(pattern);
    if (match) return typeof text === "string" ? text : text(match);
  }
  return reason;
};

const ORDER_STATUS: Record<string, string> = {
  paper_filled: "Simulated", filled: "Filled", demo_filled: "Filled", unfilled: "Not filled",
  rejected: "Rejected", canceled: "Cancelled", unknown: "Checking…", pending: "Sending…",
};

export function Dashboard() {
  const [status, setStatus] = useState<Status | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [prepare, setPrepare] = useState<Prepare | null>(null);
  const [offline, setOffline] = useState(false);
  const [budget, setBudget] = useState<string | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState("");
  // Bumped by every action: polls that started earlier can't overwrite its result.
  const revision = useRef(0);

  const refresh = useCallback(async (withPlan: boolean) => {
    const started = revision.current;
    try {
      const [nextStatus, nextPlan] = await Promise.all([
        bot<Status>("status"), withPlan ? bot<Plan>("plan") : Promise.resolve(null),
      ]);
      if (revision.current !== started) return;
      setStatus(nextStatus);
      if (nextPlan) setPlan(nextPlan);
      setOffline(false);
    } catch (e) {
      if (revision.current !== started) return;
      if (e instanceof BotError && e.offline) { setOffline(true); setStatus(null); }
    }
  }, []);

  useEffect(() => {
    let tick = 0;
    let timer: ReturnType<typeof setTimeout>;
    const loop = async () => {
      await refresh(tick % 5 === 0);
      tick += 1;
      timer = setTimeout(loop, 2_000);
    };
    void loop();
    return () => clearTimeout(timer);
  }, [refresh]);

  useEffect(() => {
    if (prepare?.state !== "running") return;
    const timer = setInterval(async () => {
      try {
        const next = await bot<Prepare>("prepare");
        setPrepare(next);
        if (next.state === "done") void refresh(true);
      } catch { /* the next status poll reports a stopped bot */ }
    }, 3_000);
    return () => clearInterval(timer);
  }, [prepare?.state, refresh]);

  async function act(action: "quickstart" | "stop" | "reconcile" | "prepare" | "resume", body: unknown = {}) {
    const mine = ++revision.current;
    setPending(action);
    setError("");
    try {
      if (action === "prepare") {
        setPrepare(await bot<Prepare>("prepare", {}));
      } else if (action === "resume") {
        await bot<Status>("reconcile", {});
        if (revision.current !== mine) return;
        const next = await bot<Status>("quickstart", body);
        if (revision.current === mine) setStatus(next);
      } else {
        const next = await bot<Status>(action, body);
        if (revision.current === mine) setStatus(next);
      }
      if (revision.current === mine) void refresh(true);
    } catch (e) {
      if (revision.current === mine) setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      if (revision.current === mine) setPending(null);
    }
  }

  if (offline) return <BotOffline />;
  if (!status) return <p className="py-24 text-center text-sm text-ash">Connecting to the bot…</p>;

  const live = status.mode === "live";
  const amount = budget ?? (status.event ? Number(status.event.budget_dollars).toFixed(2) : "");
  const validAmount = /^\d+(\.\d{1,2})?$/.test(amount) && Number(amount) > 0;
  const paused = !status.running && /uncertain|reconcile|confirmed/i.test(status.message) && status.orders.some((o) => Number(o.reserved_dollars) > 0);
  const fights = plan?.fights ?? [];
  const tradable = fights.filter((f) => f.include).length;
  const orders = status.orders;
  const payout = orders.reduce((sum, o) => sum + (Number(o.filled_count) || 0), 0);
  const eventOver = plan?.event.status === "final";
  const called = fights.filter((f) => f.winner && f.p_f1 !== null && (f.p_f1 >= 0.5 ? f.f1 : f.f2) === f.winner).length;
  const decided = fights.filter((f) => f.winner && f.p_f1 !== null).length;

  return (
    <div className="space-y-8">
      <section className="grid gap-6 lg:grid-cols-[1.25fr_1fr] lg:items-start">
        <div>
          <div className="flex flex-wrap gap-2">
            <Pill tone={live ? "bad" : "neutral"}>{live ? `Real money · cap ${usd(status.max_budget_dollars)}` : status.mode === "demo" ? "Kalshi demo" : "Practice (paper) mode"}</Pill>
            {status.in_fight_enabled && <Pill>Bets during the fight</Pill>}
            {eventOver ? <Pill tone="muted">Event finished</Pill>
              : <Pill tone={status.feed_connected ? "good" : "bad"}>{status.feed_connected ? "Fight feed live" : "Fight feed offline"}</Pill>}
            <Pill tone={status.market_connected ? "good" : "muted"}>{status.market_connected ? "Kalshi prices live" : "Kalshi prices idle"}</Pill>
          </div>
          <h1 className="display mt-4 text-4xl sm:text-5xl">{plan?.event.name || status.feed?.event_name || "Tonight's card"}</h1>
          <p className="mt-3 text-sm text-ash">
            {!plan?.card ? "Finding tonight's fights…"
              : eventOver ? `Event over · the model called ${called} of ${decided} winners`
              : `${fights.length} fights with predictions · ${tradable} the bot can bet on`}
          </p>
        </div>

        <div className="border border-ink bg-paper p-5 sm:p-6">
          {status.running ? (
            <>
              <div className="flex items-center gap-3">
                <span className="relative flex h-3 w-3"><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-hit opacity-60" /><span className="relative inline-flex h-3 w-3 rounded-full bg-hit" /></span>
                <p className="text-lg font-semibold">The bot is trading</p>
              </div>
              <Money status={status} payout={payout} />
              <button type="button" onClick={() => void act("stop")} disabled={pending === "stop"}
                className="mt-5 min-h-12 w-full bg-blood px-5 text-base font-semibold text-white hover:bg-ink disabled:opacity-60">
                {pending === "stop" ? "Stopping…" : "Stop"}
              </button>
              <p className="mt-3 text-xs leading-relaxed text-ash">It only bets when the model sees value, and never more than your limit. It may spend nothing.</p>
            </>
          ) : (
            <form onSubmit={(e) => { e.preventDefault(); if (validAmount) void act(paused ? "resume" : "quickstart", { budget_dollars: amount }); }}>
              <label htmlFor="amount" className="text-lg font-semibold">How much can the bot spend tonight?</label>
              <div className="mt-3 flex items-center border border-rail focus-within:border-ink">
                <span className="pl-4 text-2xl text-ash">$</span>
                <input id="amount" inputMode="decimal" autoComplete="off" placeholder="5.00" value={amount}
                  onChange={(e) => setBudget(e.target.value.trim())}
                  className="min-h-14 w-full bg-transparent px-2 text-2xl tabular-nums outline-none" />
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {["5", "10", "25", "50"].map((preset) => (
                  <button key={preset} type="button" onClick={() => setBudget(`${preset}.00`)}
                    className="border border-line px-3 py-1.5 text-sm hover:border-ink">${preset}</button>
                ))}
              </div>
              {status.event && Number(status.event.spent_dollars) > 0 && <Money status={status} payout={payout} />}
              <button type="submit" disabled={!validAmount || !!pending || !plan?.card || tradable === 0}
                className={`mt-5 min-h-12 w-full px-5 text-base font-semibold text-white disabled:cursor-not-allowed disabled:bg-rail ${live ? "bg-blood hover:bg-ink" : "bg-ink hover:bg-ash"}`}>
                {pending === "quickstart" || pending === "resume" ? "Starting…" : paused ? "Check orders & resume" : live ? "Start trading — real money" : "Start practice trading"}
              </button>
              {(pending === "quickstart" || pending === "resume") && (
                <button type="button" onClick={() => void act("stop")}
                  className="mt-2 min-h-11 w-full border border-blood text-sm font-semibold text-blood hover:bg-blood hover:text-white">Stop</button>
              )}
              <p className="mt-3 text-xs leading-relaxed text-ash">
                {live ? "This is real money on your Kalshi account. " : "Practice mode uses no money. "}
                The amount is the most it can spend on this event, including bets already placed. The model has no proven edge over Kalshi.
              </p>
            </form>
          )}
          {paused && !status.running && <p className="mt-3 text-sm text-gold">The bot paused to double-check an order with Kalshi. Resume checks it first.</p>}
          {error && <p role="alert" className="mt-3 text-sm text-blood">{plain(error)}</p>}
        </div>
      </section>

      {plan?.needs_predictions && (
        <Banner title="No predictions for this event yet"
          action={<button type="button" onClick={() => void act("prepare")} disabled={prepare?.state === "running" || !!pending}
            className="min-h-11 bg-ink px-4 text-sm font-semibold text-white disabled:bg-rail">{prepare?.state === "running" ? "Working…" : "Generate predictions"}</button>}>
          {prepare?.message || "This runs the model on tonight's card. It takes a minute or two."}
        </Banner>
      )}
      {eventOver ? <Banner title="This event is over">The next card shows up here automatically once ESPN and Kalshi list it.</Banner>
        : plan?.problem && !plan.needs_predictions && <Banner title={plan.problem}>{status.feed_connected ? "The bot keeps checking." : "Check that the fight feed is running."}</Banner>}

      <section>
        <div className="mb-4 flex items-baseline justify-between gap-4 border-b-2 border-ink pb-2">
          <h2 className="display text-2xl">Fights</h2>
          <p className="text-xs text-ash">Model chance vs. Kalshi price</p>
        </div>
        {fights.length === 0 ? (
          <p className="text-sm text-ash">{(status.feed?.fights ?? []).map((f) => `${f.fighter_a} vs ${f.fighter_b}`).join(" · ") || "No fights yet."}</p>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {fights.map((fight) => (
              <FightCard key={`${fight.f1}-${fight.f2}`} fight={fight}
                liveStatus={status.feed?.fights.find((f) => f.bout_id === fight.bout_id)?.status ?? fight.status}
                decision={status.decisions.find((d) => d.ticker === fight.ticker)}
                orders={orders.filter((o) => o.ticker === fight.ticker)} running={status.running} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function Money({ status, payout }: { status: Status; payout: number }) {
  return (
    <dl className="mt-5 grid grid-cols-3 gap-3 border-y border-line py-4">
      <Figure label="Limit" value={usd(status.event?.budget_dollars)} />
      <Figure label="Spent" value={usd(Number(status.event?.spent_dollars ?? 0) + Number(status.event?.reserved_dollars ?? 0))} />
      <Figure label="If all win" value={usd(payout)} />
    </dl>
  );
}

function Figure({ label, value }: { label: string; value: string }) {
  return <div><dt className="label text-[10px] text-ash">{label}</dt><dd className="mt-1 text-xl font-semibold tabular-nums">{value}</dd></div>;
}

function FightCard({ fight, liveStatus, decision, orders, running }: {
  fight: PlanFight; liveStatus: string | null; decision?: Decision; orders: Order[]; running: boolean;
}) {
  const yesBid = num(fight.yes_bid), yesAsk = num(fight.yes_ask);
  const yesIsF1 = fight.yes_fighter === fight.f1;
  const price = (forF1: boolean) => {
    if (yesAsk === null || yesBid === null) return null;
    return forF1 === yesIsF1 ? yesAsk : 1 - yesBid; // cost to buy that fighter
  };
  const quoted = decision?.p_f1;
  const model = (forF1: boolean) => {
    const base = quoted ?? fight.p_f1;
    return base === null || base === undefined ? null : forF1 ? base : 1 - base;
  };
  const other = (name: string | null) => name === fight.f1 ? fight.f2 : fight.f1;
  const chip = liveStatus === "final" ? ["Final", "muted"] : liveStatus === "in_progress" ? ["Live", "bad"]
    : fight.include ? ["Upcoming", "good"] : ["Not betting", "muted"];

  const pick = fight.p_f1 === null ? null : fight.p_f1 >= 0.5 ? fight.f1 : fight.f2;
  let activity = fight.include ? (running ? "Waiting for the next check" : "Ready") : fight.note;
  if (fight.winner) activity = `${fight.winner} won${pick ? ` — model ${pick === fight.winner ? "called it" : "missed"}` : ""}`;
  if (decision && !fight.winner) {
    activity = decision.action === "skip" ? plain(decision.reason)
      : `Bet placed: ${decision.contracts} × ${decision.side === "yes" ? fight.yes_fighter : other(fight.yes_fighter)} at ${usd(decision.price_dollars)}`;
  }

  return (
    <article className="border border-line p-5">
      <div className="flex items-center justify-between gap-3">
        <Pill tone={chip[1] as PillTone}>{chip[0]}{liveStatus === "in_progress" && fight.round ? ` · R${fight.round}` : ""}</Pill>
        {(quoted ?? fight.p_f1) != null && (
          <p className="text-xs text-ash">
            {quoted === undefined ? "Model pick" : "Live price"}:{" "}
            <strong className="text-ink">{(quoted ?? fight.p_f1 ?? 0) >= 0.5 ? fight.f1 : fight.f2}</strong>
          </p>
        )}
      </div>
      <div className="mt-4 space-y-3">
        {[true, false].map((isF1) => {
          const m = model(isF1), p = price(isF1);
          const gap = m !== null && p !== null ? Math.round((m - p) * 100) : null;
          return (
            <div key={String(isF1)}>
              <div className="flex items-baseline justify-between gap-3">
                <p className="font-semibold">{isF1 ? fight.f1 : fight.f2}{fight.winner === (isF1 ? fight.f1 : fight.f2) && <span className="ml-2 text-hit">✓</span>}</p>
                <p className="text-sm tabular-nums"><span className="font-semibold">{pct(m)}</span><span className="text-ash"> · Kalshi {cents(p)}</span>
                  {gap !== null && gap >= 5 && <span className="ml-2 text-hit">+{gap}</span>}</p>
              </div>
              <div className="mt-1.5 h-1.5 bg-line"><div className={`h-full ${m !== null && m >= 0.5 ? "bg-ink" : "bg-rail"}`} style={{ width: `${Math.round((m ?? 0) * 100)}%` }} /></div>
            </div>
          );
        })}
      </div>
      <p className={`mt-4 text-sm ${fight.winner ? (pick === fight.winner ? "font-semibold text-hit" : "font-semibold text-blood")
        : decision && decision.action !== "skip" ? "font-semibold text-hit" : "text-ash"}`}>{activity}</p>
      {orders.length > 0 && (
        <ul className="mt-3 space-y-1 border-t border-line pt-3 text-sm">
          {orders.map((o) => {
            const fighter = o.side === "yes" ? fight.yes_fighter : other(fight.yes_fighter);
            const count = Number(o.filled_count) || o.count;
            return <li key={o.id} className="flex justify-between gap-3">
              <span>{count} × {fighter} @ {usd(o.price_dollars)}{o.bout_id.includes(":r") ? ` · after R${o.bout_id.split(":r")[1]}` : ""}</span>
              <span className="text-ash">{ORDER_STATUS[o.status] ?? o.status} · pays {usd(Number(o.filled_count) || 0)}</span>
            </li>;
          })}
        </ul>
      )}
      {fight.rules_primary && (
        <details className="mt-3 text-xs text-ash">
          <summary className="cursor-pointer">Market rules</summary>
          <p className="mt-2 font-mono break-all">{fight.ticker}</p>
          <p className="mt-2 leading-relaxed">{fight.rules_primary}</p>
          {fight.rules_secondary && <p className="mt-2 leading-relaxed">{fight.rules_secondary}</p>}
        </details>
      )}
    </article>
  );
}

function Banner({ title, children, action }: { title: string; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-4 border-l-4 border-gold bg-[#faf6ee] p-4">
      <div><p className="font-semibold">{title}</p><p className="mt-1 text-sm text-ash">{children}</p></div>
      {action}
    </div>
  );
}

type PillTone = "neutral" | "good" | "bad" | "muted";
function Pill({ children, tone = "neutral" }: { children: React.ReactNode; tone?: PillTone }) {
  const tones = { neutral: "border-rail text-ash", good: "border-hit/40 text-hit", bad: "border-blood/50 text-blood", muted: "border-line text-mist" };
  return <span className={`label inline-flex items-center border px-2 py-1 text-[10px] ${tones[tone]}`}>{children}</span>;
}

function BotOffline() {
  return (
    <div className="mx-auto max-w-2xl py-16">
      <h1 className="display text-4xl">The bot isn&apos;t running</h1>
      <p className="mt-3 text-ash">Start everything with one command from the project folder, then this page connects on its own.</p>
      <Command label="Practice (no money)" command="./ictus.sh paper" />
      <Command label="Real money with a $5 cap" command="./ictus.sh live 5" />
      <p className="mt-6 text-sm text-ash">Add <code className="font-mono">--in-fight</code> to reprice from the live fight and bet while it is happening. Press Ctrl+C in that terminal to stop everything.</p>
    </div>
  );
}

function Command({ label, command }: { label: string; command: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="mt-5">
      <p className="text-sm font-medium">{label}</p>
      <div className="mt-2 flex items-center justify-between gap-3 bg-ink px-4 py-3 font-mono text-sm text-white">
        <span className="break-all">{command}</span>
        <button type="button" className="shrink-0 text-xs text-rail hover:text-white"
          onClick={() => { void navigator.clipboard.writeText(command).then(() => setCopied(true)); }}>{copied ? "Copied" : "Copy"}</button>
      </div>
    </div>
  );
}
