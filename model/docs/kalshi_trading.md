# Ictus Kalshi trading bot

The bot buys Kalshi UFC winner contracts when its own probability is clearly
above the price, inside a spending limit you set per event. It runs as a paper
simulation, on Kalshi's demo exchange, or with real money.

It does not promise a profit. The rules below are the ones the evidence
supports, and that evidence is thin: one validation backtest against sportsbook
closes and one real-money night. Nothing here has been measured against Kalshi
prices over many events. See [model evidence](trading_model_readiness.md).

## Fight night

From the repository root:

```bash
./ictus.sh              # practice, no money
./ictus.sh live 20      # real money, at most $20 on the event (asks you to type yes)
./ictus.sh stop         # stop whatever an earlier run left running
```

Then open http://localhost:3000, enter an amount, and press Start. Ctrl+C in the
terminal stops everything.

The launcher checks the setup, creates the dashboard token if it is missing,
installs the dashboard on first run, stops its own leftover processes, and
waits until all three services answer. If one fails to start it prints that
service's log. Logs are in `model/trading-state/logs/`.

The dashboard builds the session itself:

- the event comes from ESPN's live feed;
- the prediction card is the saved one whose fighters match that event. If none
  exists the bot builds it without being asked (`fetch-card`, `fetch-odds`,
  `predict`), and never overwrites an existing card;
- each fight is matched to its ESPN bout and to the Kalshi `KXUFCFIGHT` market
  whose two YES labels are the two fighters, within two days of the card's
  date. Anything ambiguous is left out with a reason.

Pressing Start confirms those markets. A fight Kalshi lists later joins the
running session by itself within about 30 seconds (see *When a fight has no
market*). A card is matched from two days back to
ten days ahead, so next weekend's card can be checked during the week. Orders
still wait for fight day.

The bot trades before and during fights. `./ictus.sh live 20 --pre-fight-only`
stops it at the opening bell. Any other option is passed to the bot, for
example `--min-edge 0.02`.

## When a fight has no market

ESPN, Kalshi, and the card (from Wikipedia) spell fighters differently, and
Kalshi does not list every fight at once. A fight is matched as a pair
(`trading/names.py`): one fighter has to match by name, and then the other may
be a nickname or short form, such as ESPN's "Bia Mesquita" for Beatriz
Mesquita. Accents, hyphens, middle names, and name order never matter.

The dashboard says which of these is true for a fight it cannot trade:

| Note | What it means | What happens |
|---|---|---|
| Kalshi has not listed this fight yet | No Kalshi market names either fighter. Early prelims are often listed late or not at all | The bot keeps checking and adds the fight to the running session when the market appears |
| Kalshi lists X vs Z, a different fight | Kalshi has one of the fighters against another opponent | No bet. The prediction is for a different matchup |
| ESPN now lists X vs Z | The opponent changed after the card was built | No bet on that fight. Delete the card's files in `model/cards` and `model/reports` and restart to rebuild it |
| Not on ESPN's card | The fight was cancelled, or ESPN has not added it | No bet |
| Two Kalshi markets match this fight | Kalshi has the matchup twice | No bet, because the bot will not guess which is right |

One failed Kalshi request does not clear the list of markets: the bot keeps
the last list it had and tries again 30 seconds later.

Checked on real data: all 14 fights of the November 7 card match Kalshi's
names for that night, and all 11 fights Kalshi had listed for November 14
match, including one the older name-by-name matching missed.

## What the bot bets

One number per fight, before and during it (`trading/signal.py`):

```
logit(p) = 1.00 · logit(sportsbook line) + 0.29 · logit(skill model)
```

- **The line** is the moneyline ESPN streams with the fight, with the margin
  removed, read at trade time. The odds saved on the card are the fallback.
- **No line, no pre-fight bet.** The skill model alone is not bet.
- **In-fight**, this number as it stood before the fight is the starting point
  for the in-play model.
- The weights were fit on train-era priced fights and are not retuned.

The card's own pick (`p_f1_wins`) is what the written report shows. The bot
does not bet it.

An order needs the bot's number to beat the all-in price (ask plus fee) by at
least 3¢. The number is first reduced for the 1.8% of fights that end in a draw
or no-contest, which Kalshi settles at 50¢.

## Trades the bot refuses

These apply even when there is an edge (`trading/guards.py`).

| Rule | What it stops |
|---|---|
| Price floor, 20¢ | Longshots. Every contract bought under 20¢ on November 7 lost. |
| One side per fight | Buying the other fighter once one is held. That only pays the fee and spread twice. |
| Falling price (in-fight) | Buying a fighter whose price fell 5¢ or more in the last 90 seconds. ESPN's stats trail the broadcast, so the market has seen something the model has not. |
| Watching period (mid-round) | Buying before the live price has been watched for 15 seconds. |
| Spaced buys (mid-round) | More than 3 buys a round, or two inside 30 seconds. No averaging down into a collapse. |
| Controlled fighter (in-fight) | A fighter trailing control time by 90 seconds and 2×, with no knockdown. A submission attempt counts only while the gap is under 3 minutes. |

## In-fight trading

The in-play model (`inplay/`, artifact `artifacts/inplay.json`) reprices a
fight from the pre-fight number plus ESPN's cumulative totals: strikes by
target, takedowns, control time, knockdowns, and submission attempts.

- **Between rounds:** ESPN must report `STATUS_END_OF_ROUND`. The bot waits 10
  seconds for the round's totals to settle and stops 40 seconds in. Up to 3
  attempts, 4 seconds apart.
- **During a round:** the bot reprices from the clock. Up to 3 buys a round, 30
  seconds apart, after the watching period. A missing, blank, or over-five-minute
  clock skips the fight.
- No trades after the final round. Finished fights stay blocked.
- Every buy on a fight shares that fight's dollar cap. Probabilities are kept
  inside 1% to 99%.

The model was trained on end-of-round totals. A mid-round number uses partial
totals that are often 30 seconds behind the broadcast, which is why the
falling-price and watching rules exist.

Retrain it with `uv run python -m octagon train-inplay`. Results are in
[reports/inplay_eval.md](../reports/inplay_eval.md). In three-round fights the
raw model was too timid, so its logit is multiplied by a slope fit on
2022–2023 (currently 1.315). Five-round fights are left alone.

Accuracy is not profit. Kalshi's live price watches the same fight, and there
are no historical in-play Kalshi prices to test against.

## Spending and data rules

| Control | Policy |
|---|---|
| Event limit | Your amount, including fees and unconfirmed orders. Live mode also has the hard cap from the command line |
| Budget split | Each fight still open gets an equal slice of the money left for its phase. Money from skipped fights flows to the rest |
| Sizing | Slice × conviction: a 10% Kelly edge gets one slice, stronger edges up to two, weaker ones less. A fight with an edge may always buy one contract. Also limited by depth |
| Per-fight ceiling | 40% of the event limit across all of that fight's bets |
| In-fight reserve | With in-fight trading on, pre-fight bets use at most 70% |
| Minimum edge | 3¢ per $1 contract after the taker fee |
| Price floor | 20¢ |
| Maximum spread | 8¢ |
| Draw or no-contest | 1.8% of fights (70 of 3,941 from 2019 on) settle at 50¢. The edge is reduced for it |
| Fighter history | At least one UFC fight for both fighters |
| Retries | A missed or partly filled order is tried again while the edge lasts: 6 times before the fight (30 s apart), 3 a round (30 s apart), 3 a break (4 s apart) |
| Feed age | Gateway packet at most 10 s old. ESPN's own timestamp at most 15 s by default; the launcher allows 600 s because ESPN often updates it only every few minutes |
| Quote | A fresh REST book before every order. A fetch slower than 5 seconds is discarded |
| Market close buffer | 60 seconds. An ESPN started-bout signal blocks pre-fight orders at once |
| Order type | Buy-only, whole contracts, immediate-or-cancel |
| Unconfirmed order | Its money stays reserved and no new order goes out until Kalshi confirms it. The session pauses only when Kalshi's record disagrees with the ledger |

Tuning options on `python -m octagon.trading` (and after the mode on
`./ictus.sh`): `--min-edge`, `--min-price`, `--max-bout-fraction`,
`--inplay-reserve`, `--min-ufc-fights`, `--draw-rate`, and `--venue-lag`.
`--venue-lag` adds a stricter pre-fight rule: Kalshi's ask must also sit below
the sportsbook line by the fee, half the spread, and 2¢. It is off by default.

There are no sales, shorts, hedges, or parlays. Only individually confirmed
`KXUFCFIGHT` winner markets are traded. Method, round, and combo markets are
rejected.

## Evidence behind the rules

**Validation backtest, 697 priced fights from 2022–2023.** Each probability was
bet against the vig-free closing line with Kalshi's fee, one contract per bet,
when it showed a 3¢ edge. Intervals resample whole events.

| Probability bet | Bets | Return | 95% interval |
|---|---:|---:|---|
| Skill model | 488 | −3.9% | −14% to +7% |
| Skill model, contracts under 20¢ only | 61 | −52% | −89% to −7% |
| Card pick (market-aware) | 199 | −2.7% | −16% to +10% |
| Line plus 0.29 × skill (what the bot bets) | 86 | +8.0% | −3% to +19% |

The stack is also the only layer with a lower log loss than the line itself
(0.6010 against 0.6035). Its bets are mostly favorites near 65¢. Only the
longshot row is clearly different from zero. A closing line with no margin is a
kinder price than a real Kalshi ask.

**In-play calibration.** In three-round fights the raw model gave the trailing
fighter 25% when that fighter won 20% of the time, in both 2022–2023 and 2024
onward. That gap is larger than the 3¢ minimum edge, so the bot kept finding
"value" on the fighter who was losing. With the slope, calibration error on the
1,662 three-round test rows fell from 0.037 to 0.025.

**November 7, 2026, real money.** The session spent $17.93 and got back $31.00.

| Phase | Spent | Returned | Result |
|---|---:|---:|---:|
| Before the fight | $5.97 | $15.00 | +$9.03 |
| Between rounds | $1.52 | $6.00 | +$4.48 |
| During rounds | $10.44 | $10.00 | −$0.44 |

Most of the profit was one underdog (Walker at 33¢, +$7.20). Mid-round buys
lost on 7 of the 9 fights they touched. Replaying that night's orders through
the guards refuses 22 of 39: 17 longshots (−$4.08), one opposite-side buy
(−$0.87), and four falling-price buys that happened to win (+$2.86). What is
left returns +$15.16 on $10.84. That is hindsight on one night. The new
probability would also have skipped the Walker bet, because the sportsbook line
agreed with Kalshi's price.

## Setup

One time, from `model`:

```bash
uv sync --locked --extra trading
cp .env.example .env   # only if there is no .env yet
```

- **Dashboard token.** `ICTUS_TRADING_TOKEN` in `model/.env` is a local secret
  between the dashboard and the bot. The launcher creates it when it is
  missing. The dashboard server reads it from that file, so it never reaches
  the browser. It is not a Kalshi key.
- **Kalshi keys.** Paper mode needs none. Demo and live need
  `KALSHI_API_KEY_ID` and `KALSHI_PRIVATE_KEY_PATH`, an absolute path to the
  PEM file. Keep the key outside the repository. Demo mode uses keys created in
  Kalshi's demo environment.
- **Odds.** `ODDS_API_KEY` is optional. It only fills the card's saved line,
  which is the fallback for ESPN's live one.
- **Live mode** sends real orders to production Kalshi. It needs the explicit
  confirmation and a hard cap the dashboard cannot exceed. The launcher asks
  for both. The whole limit can be lost.

Use a Kalshi account with no other activity in the mapped markets. Before
starting, the bot refuses to trade if the account holds positions or resting
orders it did not place there.

## Running the pieces by hand

The launcher runs these three commands. Run them yourself to change ports or
pin an event.

```bash
# in model: the ESPN fight feed (add --event-id to pin one event)
uv run --extra trading python -m octagon.live

# in model: the bot
uv run --extra trading python -m octagon.trading --mode paper --in-fight \
  --max-source-age-seconds 600

# in frontend: the dashboard
npm run dev
```

Live mode by hand:

```bash
uv run --extra trading python -m octagon.trading --mode live \
  --confirm-real-money --max-event-dollars 20 --in-fight --max-source-age-seconds 600
```

The bot listens on `127.0.0.1:8002` only. Never expose that port.

## Orders, recovery, and the journal

State is in `model/trading-state/` (gitignored). One process owns it at a time.

- **Ledger.** `ledger.sqlite3` holds every order, each session's limit, and
  each fight's result. A reservation is written before an order is sent, so a
  crash cannot lose track of money. Deleting it discards the spending history.
- **Unconfirmed orders.** The bot re-reads an unknown order from Kalshi on each
  pass and sends nothing new until it clears. If Kalshi's record disagrees with
  the ledger (identity, size, direction, or fill charges) the session pauses
  with "Order records disagree with Kalshi". A submitted order is never resent.
  A definite rejection costs nothing and does not pause the session.
- **Restart.** The bot always comes back stopped. Pressing Start on the
  dashboard checks open orders first. Fights that already have a bet keep their
  market. Other fights can be added or dropped.
- **Journal.** `observations.jsonl` records fight packets, quotes, market
  details, and every decision with its reason. It rotates at about 25 MB and
  keeps three older files, which is roughly two hours of a live card. Copy the
  files out before the next event if you want to study a whole night.
- **Price stream.** The Kalshi websocket feeds the journal and the dashboard's
  status light. Orders are always priced from a fresh REST book, so a dropped
  socket does not block trading.

Paper fills assume the displayed depth is executable. They ignore queue
position, latency, and adverse selection, and must not be read as real returns.

## Measuring results

The dashboard shows profit so far once fights finish: what the finished fights
cost, what they paid back, and what is still riding. Results come from ESPN, so
this is the bot's own tally. Kalshi's settlement is the record that counts.

For closing-line value, which says whether the bot bought at better prices than
the market's last pre-fight price:

```bash
uv run python -m octagon.trading.scorecard trading-state/observations.jsonl --settlements FILE
```

The close is the last Kalshi mid recorded while a bout was still scheduled. The
bot records it in every session.

### YouTube, headlines, and short-notice flags

The bot does not bet on these. They are measured instead. The day before or
the day of a card, the bot saves that card's context in the background
(`fetch-context`: YouTube comment lean, headline sentiment, short-notice and
late-replacement flags, debutants' pro records). After the results are in the
database:

```bash
uv run python -m octagon refresh-data
uv run python -m octagon score-context
```

That writes [reports/context_signal_eval.md](../reports/context_signal_eval.md):
the bot's number against the same number with the context applied, on every
finished fight, and how often YouTube's lean was right on its own. It gives no
verdict until the context has moved 40 finished fights.

First run, November 9, 2026: 77 finished fights on six cards, and the context
moved 7 of them. YouTube clearly leaned one way in 11 fights and was right in
5; when it disagreed with the bot's pick it was right in 1 of 7. Too few fights
to act on.

## Verification

```bash
uv run --extra trading pytest -q
uv run --extra trading ruff check src tests
```

Tests use synthetic markets and credentials. No test sends an order to an
exchange. The dashboard is checked with `npx tsc --noEmit`, `npm run lint`, and
`npm run build` in `frontend`.

API references checked October 31, 2026:
[authentication](https://docs.kalshi.com/getting_started/quick_start_authenticated_requests),
[V2 orders](https://docs.kalshi.com/api-reference/orders/create-order-v2),
[order direction](https://docs.kalshi.com/getting_started/order_direction),
[order books](https://docs.kalshi.com/getting_started/orderbook_responses),
[fills](https://docs.kalshi.com/api-reference/portfolio/get-fills),
[fee rounding](https://docs.kalshi.com/getting_started/fee_rounding), and
[UFC contract terms](https://assets.kalshi.com/contract_terms/UFCFIGHTWINNER.pdf).
