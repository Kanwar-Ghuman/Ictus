import { usd } from "@/lib/format";
import type { Plan, Status } from "@/lib/types";

/** Tonight's event, the mode the bot is in, and whether its data sources are up. */
export function EventHeader({ status, plan }: { status: Status; plan: Plan | null }) {
  const fights = plan?.fights ?? [];
  const eventOver = plan?.event.status === "final";
  const name = plan?.event.name || status.feed?.event_name || "Tonight's card";

  return (
    <div className="hero-copy">
      <p className="eyebrow">
        <Mode status={status} />
        {status.in_fight_enabled && " · Bets during the fight"}
        {" · "}
        {eventOver ? (
          <span className="text-mist">Event finished</span>
        ) : (
          <span className={status.feed_connected ? "text-hit" : "text-blood"}>
            {status.feed_connected ? "Fight feed live" : "Fight feed offline"}
          </span>
        )}
        {" · "}
        <span className={status.market_connected ? "text-hit" : "text-mist"}>
          {status.market_connected ? "Kalshi prices live" : "Kalshi prices idle"}
        </span>
      </p>
      <h1 className="hero-title">
        <span className="hero-strong">{name}</span>
        <span className="hero-mute">{summary(plan, fights, eventOver)}</span>
      </h1>
    </div>
  );
}

function Mode({ status }: { status: Status }) {
  if (status.mode === "live") return <span className="text-blood">Real money · cap {usd(status.max_budget_dollars)}</span>;
  return <span>{status.mode === "demo" ? "Kalshi demo" : "Practice (paper) mode"}</span>;
}

function summary(plan: Plan | null, fights: Plan["fights"], eventOver: boolean): string {
  if (!plan?.card) return "Finding tonight's fights…";
  if (!eventOver) {
    const tradable = fights.filter((fight) => fight.include).length;
    return `${fights.length} fights with predictions · ${tradable} the bot can bet on`;
  }
  const decided = fights.filter((fight) => fight.winner && fight.p_f1 !== null);
  const called = decided.filter((fight) => (fight.p_f1! >= 0.5 ? fight.f1 : fight.f2) === fight.winner);
  return `Event over · the model called ${called.length} of ${decided.length} winners`;
}
