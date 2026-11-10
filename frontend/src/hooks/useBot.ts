"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { bot, BotError } from "@/lib/bot";
import type { Plan, Prepare, Status } from "@/lib/types";

export type Action = "quickstart" | "stop" | "reconcile" | "prepare" | "resume";

const STATUS_EVERY_MS = 2_000;
const PLAN_EVERY_POLLS = 5; // the plan asks Kalshi for its markets, so it refreshes less often
const PREPARE_EVERY_MS = 3_000;

/** Everything the dashboard knows about the bot, kept fresh, plus the buttons' actions. */
export function useBot() {
  const [status, setStatus] = useState<Status | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [prepare, setPrepare] = useState<Prepare | null>(null);
  const [offline, setOffline] = useState(false);
  const [pending, setPending] = useState<Action | null>(null);
  const [error, setError] = useState("");
  // Bumped by every action: polls that started earlier can't overwrite its result.
  const revision = useRef(0);

  const refresh = useCallback(async (withPlan: boolean) => {
    const started = revision.current;
    try {
      const [nextStatus, nextPlan] = await Promise.all([
        bot<Status>("status"),
        withPlan ? bot<Plan>("plan") : Promise.resolve(null),
      ]);
      if (revision.current !== started) return;
      setStatus(nextStatus);
      if (nextPlan) setPlan(nextPlan);
      setOffline(false);
    } catch (e) {
      if (revision.current !== started) return;
      if (e instanceof BotError && e.offline) {
        setOffline(true);
        setStatus(null);
      }
    }
  }, []);

  useEffect(() => {
    let polls = 0;
    let timer: ReturnType<typeof setTimeout>;
    const loop = async () => {
      await refresh(polls % PLAN_EVERY_POLLS === 0);
      polls += 1;
      timer = setTimeout(loop, STATUS_EVERY_MS);
    };
    void loop();
    return () => clearTimeout(timer);
  }, [refresh]);

  // The bot starts the model by itself when a card has no predictions. Follow
  // its progress until it finishes or fails.
  const needsPredictions = plan?.needs_predictions === true;
  const prepareStuck = prepare?.state === "failed" || prepare?.state === "unavailable";
  const preparing = needsPredictions && !prepareStuck;
  useEffect(() => {
    if (!preparing) return;
    const check = async () => {
      try {
        const next = await bot<Prepare>("prepare");
        setPrepare(next);
        if (next.state === "done") void refresh(true);
      } catch {
        // The next status poll reports a stopped bot.
      }
    };
    void check();
    const timer = setInterval(check, PREPARE_EVERY_MS);
    return () => clearInterval(timer);
  }, [preparing, refresh]);

  async function act(action: Action, body: unknown = {}) {
    const mine = ++revision.current;
    setPending(action);
    setError("");
    try {
      if (action === "prepare") {
        setPrepare(await bot<Prepare>("prepare", {}));
      } else if (action === "resume") {
        // Check the unconfirmed order with Kalshi first, then start again.
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

  return { status, plan, prepare, offline, pending, error, needsPredictions, prepareStuck, act };
}
