// What the trading bot sends the dashboard. Amounts are dollar strings.

export type Mode = "paper" | "demo" | "live";

export type Decision = {
  ticker: string;
  bout: string;
  action: "skip" | Mode;
  reason: string;
  side?: string;
  probability?: number;
  p_f1?: number;
  price_dollars?: string;
  contracts?: number;
  cost_dollars?: string;
  edge?: number;
  phase?: string;
};

export type Order = {
  id: string;
  bout_id: string;
  ticker: string;
  side: string;
  count: number;
  price_dollars: string;
  cost_dollars: string;
  reserved_dollars: string;
  status: string;
  filled_count: string;
};

export type MarketResult = {
  fighter: string;
  outcome: "open" | "won" | "lost" | "split";
  cost_dollars: string;
  returned_dollars: string;
  contracts: string;
};

export type Results = {
  settled_cost_dollars: string;
  returned_dollars: string;
  profit_dollars: string;
  open_cost_dollars: string;
  open_payout_dollars: string;
  markets: Record<string, MarketResult>;
};

export type EventMoney = {
  budget_dollars: string;
  spent_dollars: string;
  reserved_dollars: string;
  remaining_dollars: string;
};

export type FeedFight = { bout_id: string; status: string; fighter_a: string; fighter_b: string };

export type Status = {
  mode: Mode;
  running: boolean;
  feed_connected: boolean;
  market_connected: boolean;
  max_budget_dollars?: string | null;
  in_fight_enabled?: boolean;
  message: string;
  event: EventMoney | null;
  decisions: Decision[];
  orders: Order[];
  results: Results | null;
  feed: null | { event_name: string; fights: FeedFight[] };
};

/** The model's own call for a fight. Shown, never bet. */
export type ModelPick = {
  winner: string;
  confidence: number | null;
  method: string | null; // "KO/TKO", "SUB" or "DEC"
  round: number | null; // null for a decision
  exact_probability: number | null;
};

export type PlanFight = {
  f1: string;
  f2: string;
  p_f1: number | null;
  line: string | null;
  pick: ModelPick | null;
  weight_class: string | null;
  /** How a finished fight ended, in ESPN's words. */
  result: null | { method: string | null; round: number | null };
  bout_id: string | null;
  status: string | null;
  round: number | null;
  ticker: string | null;
  yes_fighter: string | null;
  yes_bid: string | null;
  yes_ask: string | null;
  rules_primary: string | null;
  rules_secondary: string | null;
  include: boolean;
  note: string;
  winner: string | null;
};

export type Plan = {
  event: { name: string | null; status: string | null };
  card: null | { slug: string; event: string; date: string };
  fights: PlanFight[];
  problem: string | null;
  needs_predictions?: boolean;
};

export type Prepare = {
  state: "idle" | "running" | "done" | "failed" | "unavailable";
  message: string;
};
