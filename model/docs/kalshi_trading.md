# Ictus Kalshi trading lab

This integration runs **paper simulations, Kalshi demo orders, or opt-in live
orders** with an event spending ceiling. In-fight trading is disabled. It
does not promise a profit, optimize a proven profitable policy, or improve the
model's measured predictive accuracy. The existing results do not establish a
trading edge: see [model evidence](trading_model_readiness.md).

## What is implemented

- A local `/trading` dashboard for an event budget, explicit fight/market
  mappings, order status, skipped decisions, Stop, and reconciliation.
- A server-side consumer of the existing ESPN gateway WebSocket. Missing,
  stale, mismatched, started, finished, and unknown bouts block new orders.
- Optional authenticated Kalshi market WebSocket snapshots/deltas, with
  subscription sequence checks and invalidation on a gap or disconnect.
  Public REST quotes work without Kalshi credentials in paper mode.
- A conservative buy-only policy using frozen `p_skill`, actual ask depth,
  fee metadata, and small allocations. It can leave the entire budget unused.
- A persistent SQLite order ledger. Reservations precede submission; uncertain
  outcomes retain money and pause the session. Restart always returns paused.
- RSA/Ed25519 signing, current V2 IOC orders, full cursor pagination, and exact
  fixed-point arithmetic. There are no automatic order submission retries.
- Local, rotating observation journals for future research, and evaluation
  checks that prevent later-tuned parameters from masquerading as held-out work.

The initial supported instruments are individually confirmed **KXUFCFIGHT
winner-series** contracts. Method, round, combo, and parlay contracts require
different probabilities and are rejected. Every bout gets at most one order
attempt. A failed or unfilled attempt does not automatically retry that bout.

## Quick start

After the one-time setup below (dependencies, `ICTUS_TRADING_TOKEN`, Kalshi key):

```bash
./ictus.sh paper            # from the repository root; practice, no money
./ictus.sh live 5           # real money, at most $5 per event (asks you to type yes)
```

Open http://localhost:3000, enter the amount, press Start. The dashboard builds
the session itself: the ESPN event from the live feed, the prediction card whose
fighters match it ("Generate predictions" runs `fetch-card` + `predict` when none
exists, never overwriting an existing card), each ESPN bout by fighter names,
and each Kalshi winner market whose two YES labels are exactly the two fighters
on the card's date. Names must match exactly after accent and punctuation
folding; anything ambiguous is left out with a reason. Pressing Start is the
confirmation for those markets; the service still validates every mapping.
Fights that already have a bet keep their original market; other fights can be
added or dropped when you restart with a new amount. The launcher uses
`--max-source-age-seconds 600` and Kelly-limited sizing without extra per-order
or per-fight caps (`--max-order-fraction 1 --max-bout-fraction 1 --kelly-fraction 1`).

The sections below describe the underlying commands and every safety rule.

## Start locally (manual)

From the repository's `model` directory:

```bash
uv sync --locked --extra trading
cp .env.example .env  # only if you do not already have a .env file
```

Keep existing `.env` entries. Set `ICTUS_TRADING_TOKEN` to a separate random
secret of at least 32 characters. To generate one locally:

```bash
python -c 'import secrets; print(secrets.token_urlsafe(32))'
```

This token authorizes local dashboard controls. Enter it only into the local
dashboard. It is kept in the tab's memory, not local/session storage or a URL.
Never use a Kalshi private key as the dashboard token.

Run the existing gateway, pinned to the correct ESPN event:

```bash
uv run --extra trading python -m octagon.live --event-id YOUR_ESPN_EVENT_ID
```

In another terminal in `model`, start the paused paper service:

```bash
uv run --extra trading python -m octagon.trading --mode paper
```

In `frontend`, run `npm run dev` and open
`http://localhost:3000/trading`. The trading service is separately bound to
`127.0.0.1:8002`. The existing prediction API remains read-only and unchanged.
The hosted static prediction snapshot is never used as trading state.

1. Connect with `ICTUS_TRADING_TOKEN`.
2. Select a model card and enter the matching ESPN event ID and maximum event
   spending amount in dollars.
3. For each desired bout, select its exact ESPN ID, enter the Kalshi ticker,
   select the fighter represented by YES, load the market, read all settlement
   rules, and confirm the mapping. Automatic fuzzy matching is deliberately absent.
4. Save the configuration. Start paper trading only after reviewing it.
5. Watch skip reasons, spent funds, reservations, and remaining budget. Stop
   halts new submissions. Reconcile is available while stopped.

The service checks both fighter identities, the exact YES label, winner series,
market occurrence date, current status and rules, and the configured ESPN event.
Changing an event budget or mappings requires stopping and reviewing again.
Start is bound to the reviewed configuration and server instance: another tab's
changes or a service restart invalidate it. Funds already spent or reserved
cannot be erased by saving the same event again.

## Kalshi credentials and demo

Paper mode needs no Kalshi keys for public REST market data. For the market
WebSocket, set `KALSHI_API_KEY_ID` and `KALSHI_PRIVATE_KEY_PATH` in `model/.env`.
The latter is an **absolute path** to the downloaded PEM key file. Keep keys
outside the repository where practical; `.env`, `*.key`, and `*.pem` are ignored.
Do not paste credentials into the browser or chat.

Use credentials created in Kalshi's **demo environment** for demo execution:

```bash
uv run --extra trading python -m octagon.trading --mode demo
```

The service pins demo orders to the demo exchange. Production credentials
support read-only production market data in paper mode.

### Live (real-money) mode

Live mode sends real orders to production Kalshi. It needs production API
credentials, an explicit confirmation flag, and a hard per-event dollar cap the
dashboard cannot exceed:

```bash
uv run --extra trading python -m octagon.trading --mode live \
  --confirm-real-money --max-event-dollars 5
```

`--max-order-fraction`, `--max-bout-fraction` and `--kelly-fraction` (each in
(0, 1]) loosen the default 5% / 10% / quarter-Kelly sizing. Kelly is never
exceeded, so even fully loosened sizing can leave most of a small budget unused.
Every other check (feed freshness, started-bout block, exact market identity,
account preflight, one attempt per bout, reconciliation) is unchanged. Live
mode does not create an edge: nothing in [model evidence](trading_model_readiness.md)
shows these orders are profitable, and the whole budget can be lost.

Demo markets, prices, liquidity, and available series can differ from production.
If an actual KXUFCFIGHT winner market is absent there, the service abstains; it
does not substitute an unrelated instrument. Demo acceptance and private fill
reconciliation have been tested with fixtures, **not a funded/demo account**.
No credentials were supplied and no real or demo orders were placed during
implementation. Public production series/market metadata was checked read-only.

Use a dedicated demo account without unrelated trading in the mapped markets.
Before starting, unexplained open orders or holdings in unattempted markets
block execution. The event ledger is not a complete account-management system.

### In-fight (between-rounds) mode

`--in-fight` adds a second decision path that trades **only during the break
between rounds**, using the between-rounds model in `artifacts/inplay.json`
(train/evaluate it with `uv run python -m octagon train-inplay`; results are in
[reports/inplay_eval.md](../reports/inplay_eval.md)). It is off by default.

```bash
uv run --extra trading python -m octagon.trading --mode paper --in-fight \
  --max-source-age-seconds 600
```

- Inputs: the Kalshi mid recorded while the bout was still scheduled
  (`trading-state/prefight_prices.json`, refreshed every 10 s) — or, if none was
  captured, the skill model's `p_skill` with the 3-UFC-fight history rule —
  plus ESPN's cumulative totals (strikes by target, takedowns, control time,
  knockdowns, submission attempts) at the end of round k.
- Window: ESPN must report `STATUS_END_OF_ROUND`; the bot waits 10 s for round
  totals to settle and refuses after 40 s, because ESPN keeps showing the break
  ~30 s into the next round. Never during live action, never after the final round.
- One attempt per bout per break (`<bout>:r<k>` in the ledger); every attempt on a
  bout shares the per-bout cap. Probabilities are clamped to [1%, 99%].
- Finished/unavailable bouts are still blocked permanently.

The model is far more accurate than the pre-fight prior (2024–26 test: 63% → 75%
accuracy, 80% after round 2), but **Kalshi's live price also watches the fight**.
On the first live check (Brown vs Smith, Oct 31) the model and Kalshi agreed
within a few cents at both breaks, and no trade would have cleared the margin.
Run it in paper mode across several events, then compare paper results and
break-time prices before risking money.

### Startup flags learned on the first live night

- `--max-source-age-seconds 600`: ESPN's `espn_updated_at` often moves only every
  1–8 minutes, even mid-fight; the 15 s default blocks everything.
- Market data turns green only after a configuration is saved (subscriptions
  follow the mapped tickers).
- A session that has spent money keeps its exact mappings. To change fights, start
  a fresh ledger with `--state-dir trading-state/<new>` and lower
  `--max-event-dollars` by what was already spent.

## Spending and data rules

| Control | Initial policy |
|---|---|
| Total event ceiling | User amount, including fees and unresolved reservations |
| Per-order allocation | At most 5% of the event budget |
| Per-bout allocation | At most 10%; currently one attempt means the order cap binds |
| Sizing | Quarter Kelly, further constrained by budget, depth, and order caps |
| Probability haircut | 5 percentage points; a policy margin, not a confidence interval |
| Minimum remaining edge | 4 percentage points after haircut and reserved per-contract fees |
| Maximum spread | 8 cents |
| Fighter history | At least three UFC fights for both fighters |
| Feed receipt/source age | At most 10 / 15 seconds; future/missing times rejected |
| Quote age | At most 5 seconds, with a fresh REST confirmation before submission |
| Market close buffer | 60 seconds; an ESPN started-bout signal blocks immediately |
| Order type | Buy-only, whole-contract requested quantity, immediate-or-cancel |

Whole-contract orders can still receive fractional fills. Reconciliation reads
every fill page, checks identities and directions, and calculates cost from
the purchased side's price plus the reported fee. It waits until quantities
match the terminal order. It does not infer a cancellation from an empty page
or release reservations from an ambiguous NO-side aggregate cost.

The event ceiling limits cumulative purchases; sale proceeds or settlements
are not recycled into it. There are no short sales, leverage, automatic exits,
portfolio hedges, or compound-bet probability assumptions. Paper fills assume
displayed depth is executable; they do not model queue priority, latency losses,
or adverse selection and must not be described as real returns. The dashboard
reports spending, not realized P&L; settlement accounting remains future work.

Kalshi's UFC rules include $0.50 draw/no-contest settlements and fair-price
settlement in certain cancellation/postponement cases. Existing model training
uses decisive fights. Its probability is therefore not a fully modeled
expected contract payout under every settlement outcome. This is another
reason these rules are experimental and production execution is disabled.

## Recovery and evidence

State defaults to `model/trading-state/` (gitignored). Keep the SQLite ledger:
deleting it discards budget history. One service process owns a state directory
using an OS file lock (macOS/Linux). Do not run separate journals for the same
account/event and assume they share a spending cap.

After a restart or timeout, inspect the ledger and use Reconcile while stopped.
Accepted-but-unknown orders retain their reservations; an empty response is not
proof that no order exists. Definitive submission rejections consume no budget
but retain the attempted-bout record. Stop cannot undo an order already accepted
by the exchange; IOC limits avoid leaving intentionally resting orders.

`observations.jsonl` records source packets, receipt timestamps, quotes, market
metadata, and decisions. It rotates at about 25 MB with three prior files.
Archive these before rotation if preserving a research dataset. This is an
evidence recorder, not an independently validated replay/backtest or a complete
settlement ledger. The next model phase needs event-separated in-play training
data, realistic execution replay, and untouched forward evaluation.

## Verification and upstream contracts

```bash
uv run --extra trading pytest -q
uv run --extra trading ruff check src tests
```

The frontend also passes lint, TypeScript checking, production build, and
mocked browser journeys. Tests use synthetic markets and credentials; no test
submits an order to an exchange.

API references checked October 31, 2026:
[authentication](https://docs.kalshi.com/getting_started/quick_start_authenticated_requests),
[V2 orders](https://docs.kalshi.com/api-reference/orders/create-order-v2),
[order direction](https://docs.kalshi.com/getting_started/order_direction),
[order books](https://docs.kalshi.com/getting_started/orderbook_responses),
[fills](https://docs.kalshi.com/api-reference/portfolio/get-fills),
[fee rounding](https://docs.kalshi.com/getting_started/fee_rounding), and
[UFC contract terms](https://assets.kalshi.com/contract_terms/UFCFIGHTWINNER.pdf).
