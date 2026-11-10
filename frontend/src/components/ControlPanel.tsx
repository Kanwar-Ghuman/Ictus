"use client";

import { useState } from "react";

import { Money } from "@/components/Money";
import type { Action } from "@/hooks/useBot";
import { plain } from "@/lib/reasons";
import type { Status } from "@/lib/types";

type Props = {
  status: Status;
  /** False until tonight's card has predictions and at least one fight to bet on. */
  canStart: boolean;
  pending: Action | null;
  error: string;
  act: (action: Action, body?: unknown) => Promise<void>;
};

const PRESETS = ["5", "10", "25", "50"];
const AMOUNT = /^\d+(\.\d{1,2})?$/;

function Chevron() {
  return (
    <svg className="btn-chevron" width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
      <path d="M3 1.5 6.5 5 3 8.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** The box on the right: set a limit and start, or watch the money and stop. */
export function ControlPanel({ status, canStart, pending, error, act }: Props) {
  const [typed, setTyped] = useState<string | null>(null);
  const amount = typed ?? (status.event ? Number(status.event.budget_dollars).toFixed(2) : "");
  const validAmount = AMOUNT.test(amount) && Number(amount) > 0;
  // The bot stopped itself because Kalshi has not confirmed an order yet.
  const awaitingOrder = !status.running
    && /uncertain|reconcile|confirmed/i.test(status.message)
    && status.orders.some((order) => Number(order.reserved_dollars) > 0);

  return (
    <div className="control">
      {status.running ? (
        <Running status={status} stopping={pending === "stop"} onStop={() => void act("stop")} />
      ) : (
        <StartForm status={status} amount={amount} onAmount={setTyped}
          canSubmit={validAmount && !pending && canStart}
          starting={pending === "quickstart" || pending === "resume"}
          awaitingOrder={awaitingOrder}
          onStart={() => void act(awaitingOrder ? "resume" : "quickstart", { budget_dollars: amount })}
          onStop={() => void act("stop")} />
      )}
      {awaitingOrder && (
        <p className="fine fine-warn">
          The bot paused to double-check an order with Kalshi. Resume checks it first.
        </p>
      )}
      {error && <p role="alert" className="fine fine-bad">{plain(error)}</p>}
    </div>
  );
}

function Running({ status, stopping, onStop }: { status: Status; stopping: boolean; onStop: () => void }) {
  return (
    <>
      <div className="running-head">
        <span className="live-dot" aria-hidden="true"><i /><b /></span>
        <p className="ask ask-lg">The bot is trading</p>
      </div>
      <Money status={status} />
      <div className="btn-row">
        <button type="button" onClick={onStop} disabled={stopping} className="btn btn-danger">
          {stopping ? "Stopping…" : "Stop"}
        </button>
      </div>
      <p className="fine">
        It bets only when Kalshi&apos;s price is clearly better than the sportsbook odds and the
        model together, and never more than your limit. Most fights get no bet.
      </p>
    </>
  );
}

function StartForm({ status, amount, onAmount, canSubmit, starting, awaitingOrder, onStart, onStop }: {
  status: Status; amount: string; onAmount: (value: string) => void; canSubmit: boolean;
  starting: boolean; awaitingOrder: boolean; onStart: () => void; onStop: () => void;
}) {
  const live = status.mode === "live";
  const label = starting ? "Starting…"
    : awaitingOrder ? "Check orders & resume"
    : live ? "Start trading — real money"
    : "Start practice trading";
  const alreadySpent = status.event && Number(status.event.spent_dollars) > 0;

  return (
    <form onSubmit={(event) => { event.preventDefault(); if (canSubmit) onStart(); }}>
      <label htmlFor="amount" className="ask">How much can the bot spend tonight?</label>
      <div className="amount">
        <span className="amount-sign">$</span>
        <input id="amount" inputMode="decimal" autoComplete="off" placeholder="5.00" value={amount}
          onChange={(event) => onAmount(event.target.value.trim())} />
      </div>
      <div className="chips">
        {PRESETS.map((preset) => (
          <button key={preset} type="button" className="chip" onClick={() => onAmount(`${preset}.00`)}>
            ${preset}
          </button>
        ))}
      </div>
      {alreadySpent && <Money status={status} />}
      <div className="btn-row">
        <button type="submit" disabled={!canSubmit} className={live ? "btn btn-danger" : "btn btn-primary"}>
          {label}
          <Chevron />
        </button>
        {starting && (
          <button type="button" onClick={onStop} className="btn btn-quiet">
            Stop
          </button>
        )}
      </div>
      <p className="fine">
        {live ? "This is real money on your Kalshi account. " : "Practice mode uses no money. "}
        The amount is the most it can spend on this event, including bets already placed. The
        model has no proven edge over Kalshi.
      </p>
    </form>
  );
}
