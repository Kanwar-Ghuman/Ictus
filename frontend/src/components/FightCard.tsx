import { Pill, type PillTone } from "@/components/ui";
import { cents, num, pct, signedUsd, usd } from "@/lib/format";
import { orderStatus, orderTiming, plain } from "@/lib/reasons";
import type { Decision, MarketResult, Order, PlanFight } from "@/lib/types";

type Props = {
  fight: PlanFight;
  /** The freshest status for this bout: the live feed's, else the plan's. */
  liveStatus: string | null;
  decision?: Decision;
  result?: MarketResult;
  orders: Order[];
  running: boolean;
};

// Show the gap between the bot's chance and Kalshi's price once it is this big.
const NOTABLE_GAP_CENTS = 5;

export function FightCard({ fight, liveStatus, decision, result, orders, running }: Props) {
  const live = liveStatus === "in_progress";
  // During a fight the bot's latest decision carries its updated chance.
  const chance = decision?.p_f1 ?? fight.p_f1;
  const settled = result && result.outcome !== "open" ? result : null;
  const net = settled ? Number(settled.returned_dollars) - Number(settled.cost_dollars) : 0;
  const placed = decision && decision.action !== "skip" && !fight.winner;
  const highlight = settled ? (net >= 0 ? "font-semibold text-hit" : "font-semibold text-blood")
    : placed ? "font-semibold text-hit" : "text-ash";

  return (
    <article className="sheet fight">
      <div className="fight-top">
        <StatusChip fight={fight} liveStatus={liveStatus} />
        {chance != null && (
          <p className="fight-read">
            {decision?.p_f1 !== undefined && live ? "Live read" : fight.line ? "Odds + model" : "Model only, no odds"}:{" "}
            <strong>{chance >= 0.5 ? fight.f1 : fight.f2}</strong>
          </p>
        )}
      </div>

      <div className="fight-rows">
        <FighterRow name={fight.f1} chance={chance ?? null} price={priceToBuy(fight, true)}
          won={fight.winner === fight.f1} />
        <FighterRow name={fight.f2} chance={chance == null ? null : 1 - chance}
          price={priceToBuy(fight, false)} won={fight.winner === fight.f2} />
      </div>

      <p className={`fight-line ${highlight}`}>{activity(fight, decision, settled, net, running)}</p>
      {orders.length > 0 && <OrderList fight={fight} orders={orders} />}
      {fight.rules_primary && (
        <details className="rules">
          <summary className="cursor-pointer">Market rules</summary>
          <p className="mt-2 font-mono break-all">{fight.ticker}</p>
          <p className="mt-2 leading-relaxed">{fight.rules_primary}</p>
          {fight.rules_secondary && <p className="mt-2 leading-relaxed">{fight.rules_secondary}</p>}
        </details>
      )}
    </article>
  );
}

function StatusChip({ fight, liveStatus }: { fight: PlanFight; liveStatus: string | null }) {
  const [label, tone]: [string, PillTone] = liveStatus === "final" ? ["Final", "muted"]
    : liveStatus === "in_progress" ? ["Live", "bad"]
    : fight.include ? ["Upcoming", "good"]
    : ["Not betting", "muted"];
  const round = liveStatus === "in_progress" && fight.round ? ` · R${fight.round}` : "";
  return <Pill tone={tone}>{label}{round}</Pill>;
}

function FighterRow({ name, chance, price, won }: {
  name: string; chance: number | null; price: number | null; won: boolean;
}) {
  const gap = chance !== null && price !== null ? Math.round((chance - price) * 100) : null;
  const favored = chance !== null && chance >= 0.5;
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <p className="fighter-name">
          {name}
          {won && <span className="ml-2 text-hit">✓</span>}
        </p>
        <p className="fighter-meta">
          <span className="font-medium text-ink">{pct(chance)}</span>
          <span className="quiet"> · Kalshi {cents(price)}</span>
          {gap !== null && gap >= NOTABLE_GAP_CENTS && <span className="ml-2 text-hit">+{gap}</span>}
        </p>
      </div>
      <div className="meter">
        <div className={`meter-fill ${favored ? "meter-hot" : ""}`}
          style={{ width: `${Math.round((chance ?? 0) * 100)}%` }} />
      </div>
    </div>
  );
}

function OrderList({ fight, orders }: { fight: PlanFight; orders: Order[] }) {
  return (
    <ul className="orders">
      {orders.map((order) => {
        const filled = Number(order.filled_count) || 0;
        return (
          <li key={order.id} className="flex justify-between gap-3">
            <span>
              {filled || order.count} × {sideFighter(fight, order.side)} @ {usd(order.price_dollars)}
              {orderTiming(order.bout_id)}
            </span>
            <span className="text-mist">{orderStatus(order.status)} · pays {usd(filled)}</span>
          </li>
        );
      })}
    </ul>
  );
}

/** The fighter a YES or NO contract backs in this fight's market. */
function sideFighter(fight: PlanFight, side: string | undefined): string {
  const yes = fight.yes_fighter ?? fight.f1;
  if (side === "yes") return yes;
  return yes === fight.f1 ? fight.f2 : fight.f1;
}

/** What one contract on this fighter costs right now, from the market's YES quote. */
function priceToBuy(fight: PlanFight, forF1: boolean): number | null {
  const yesBid = num(fight.yes_bid), yesAsk = num(fight.yes_ask);
  if (yesAsk === null || yesBid === null) return null;
  const yesIsF1 = fight.yes_fighter === fight.f1;
  return forF1 === yesIsF1 ? yesAsk : 1 - yesBid;
}

/** The one line under a fight that says what is happening with it. */
function activity(fight: PlanFight, decision: Decision | undefined, settled: MarketResult | null,
                  net: number, running: boolean): string {
  if (settled) {
    const outcome = settled.outcome === "split" ? "was refunded at half" : settled.outcome;
    const headline = fight.winner ? `${fight.winner} won` : "No winner";
    return `${headline} — your bet on ${settled.fighter} ${outcome} (${signedUsd(net)})`;
  }
  if (fight.winner) {
    if (fight.p_f1 === null) return `${fight.winner} won`;
    const pick = fight.p_f1 >= 0.5 ? fight.f1 : fight.f2;
    return `${fight.winner} won — the bot ${pick === fight.winner ? "called it" : "missed"}`;
  }
  if (decision) {
    if (decision.action === "skip") return plain(decision.reason);
    const fighter = sideFighter(fight, decision.side);
    return `Bet placed: ${decision.contracts} × ${fighter} at ${usd(decision.price_dollars)}`;
  }
  if (!fight.include) return fight.note;
  return running ? "Waiting for the next check" : "Ready";
}
