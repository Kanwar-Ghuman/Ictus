// The bot explains every skipped fight in its own terms. These turn that into
// one plain sentence. Anything not listed is shown as the bot wrote it.

type Rewrite = string | ((match: RegExpMatchArray) => string);

const REASONS: Array<[RegExp, Rewrite]> = [
  [/^No edge: model (\d+)% on (.+?) vs (\d+)¢ all-in/,
    (m) => `Watching — the bot gives ${m[2]} ${m[1]}%, Kalshi wants ${m[3]}¢ (not cheap enough)`],
  [/^Longshot: (\d+)¢/, (m) => `Skipping — ${m[1]}¢ is a longshot, and longshots lose money`],
  [/^Price is falling fast: (\d+)¢ to (\d+)¢/,
    (m) => `Holding off — the price just dropped from ${m[1]}¢ to ${m[2]}¢, so something happened in the fight`],
  [/Watching the live price/i, "Fight is live — watching the price before buying"],
  [/^Sticking with (.+?);/, (m) => `Already on ${m[1]} — the bot never bets both fighters`],
  [/^Staying off (.+?);/, (m) => `Skipping ${m[1]} — being controlled with no way to finish`],
  [/No sportsbook line/i, "No sportsbook odds for this fight yet — no bet before it starts"],
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
  [/fight feed disconnected|feed reports an error|ESPN source timestamp|Gateway timestamp/i,
    "Waiting for the fight feed"],
  [/websocket book|quote retrieval|Two-sided market/i, "Waiting for Kalshi prices"],
  [/Insufficient fighter history/i, "Skipped — not enough UFC history for the model"],
  [/Market is not open|closing|closed/i, "Kalshi market is closed"],
  [/Insufficient account cash/i, "Not enough cash in your Kalshi account"],
  [/budget exhausted/i, "Spending limit reached"],
];

export function plain(reason: string): string {
  for (const [pattern, rewrite] of REASONS) {
    const match = reason.match(pattern);
    if (match) return typeof rewrite === "string" ? rewrite : rewrite(match);
  }
  return reason;
}

const ORDER_STATUS: Record<string, string> = {
  paper_filled: "Simulated",
  filled: "Filled",
  demo_filled: "Filled",
  unfilled: "Not filled",
  rejected: "Rejected",
  canceled: "Cancelled",
  unknown: "Checking…",
  pending: "Sending…",
};

export function orderStatus(status: string): string {
  return ORDER_STATUS[status] ?? status;
}

/** When an order was placed, from its key: "401:r2" is the break after round 2, "401:l1:3" a buy during round 1. */
export function orderTiming(attempt: string): string {
  const [, phase] = attempt.split(":");
  if (!phase || phase.startsWith("p")) return "";
  return phase.startsWith("r") ? ` · after R${phase.slice(1)}` : ` · during R${phase.slice(1)}`;
}
