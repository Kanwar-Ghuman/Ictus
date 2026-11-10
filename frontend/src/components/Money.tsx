import { Figure } from "@/components/ui";
import { signedUsd, usd } from "@/lib/format";
import type { Status } from "@/lib/types";

/** The limit, what is spent, and the profit once any fight has finished. */
export function Money({ status }: { status: Status }) {
  const results = status.results;
  const spent = Number(status.event?.spent_dollars ?? 0) + Number(status.event?.reserved_dollars ?? 0);
  const profit = Number(results?.profit_dollars ?? 0);
  const anySettled = Number(results?.settled_cost_dollars ?? 0) > 0;
  const stillRiding = Number(results?.open_cost_dollars ?? 0);

  return (
    <>
      <dl className="money-row">
        <Figure label="Limit" value={usd(status.event?.budget_dollars)} />
        <Figure label="Spent" value={usd(spent)} />
        {anySettled ? (
          <Figure label={status.mode === "paper" ? "Practice profit" : "Profit so far"}
            tone={profit >= 0 ? "good" : "bad"} value={signedUsd(profit)} />
        ) : (
          <Figure label="If all win" value={usd(results?.open_payout_dollars)} />
        )}
      </dl>
      {anySettled && (
        <p className="fine">
          Finished fights cost {usd(results?.settled_cost_dollars)} and paid
          back {usd(results?.returned_dollars)}.
          {stillRiding > 0
            && ` Still riding: ${usd(stillRiding)}, worth ${usd(results?.open_payout_dollars)} if every one wins.`}
        </p>
      )}
    </>
  );
}
