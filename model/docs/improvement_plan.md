# Ictus improvement plan

Reviewed November 6, 2026 against the committed evaluation reports
(`evaluation_valid.md`, `evaluation_test.md`, `backtest_valid.md`,
`inplay_eval.md`) and the current trading policy in `trading/risk.py`.

This is a plan, not a claim that any change below is already profitable.
The existing evidence says the opposite of "loosen the bot."

## What the code does now

Shipped with the plan, without a retrain. The fight database is not in this
tree, so cardio slope, the opponent graph, and a refit of the in-play ratios
are still waiting on `build-features` and a walk-forward.

- `quality_win_rate` is elite wins over elite fights, and only once there are
  two of them. `quality_n` is the count. The saved artifact, if you have one
  locally, was fit on the old column. Rebuild and retrain before treating a
  new feature table as the model the bot loads. Do not promote it unless the
  validation stack log loss improves or stays inside 0.002.
- `python -m octagon.trading.scorecard JOURNAL --settlements FILE` prints mean
  closing-line value in cents, settlement ROI, and an event-block interval.
  The close is the last pre-fight Kalshi mid in `observations.jsonl`.
- Pre-fight orders use the pure stack, `a=1.00` and `b=0.29`, and abstain when
  the bout has no `p_market`. `edge_of` applies `p + d·(0.5−p)`. `d` stays 0
  until `--draw-rate` is set from the KXUFCFIGHT rules.
- Mid-round orders are refused. Break orders are unchanged.
- `--venue-lag` requires a same-time `p_book` and a Kalshi ask that lags it by
  the fee, half the spread, and 2¢. The flag is off until a scorecard shows
  pre-fight closing-line value at or above zero.
- Sizing is the old policy: 40% bout cap, equal slices, one-contract floor.
  That waits on the closing-line gate. Do not lower the 3¢ edge to get more bets.

## Verdict

The winner model is a competent pre-fight picker and a losing bettor.

| Question the number answers | Result | Source |
|---|---|---|
| Can it pick a winner better than chance? | Test 2024–Sep 12 2026: blend **65.2%** accuracy, log loss **0.628**, n=1,414 | `evaluation_test.md` |
| Does it know more than the vig-free close? | No. Validation priced subset, n=697: market log loss **0.6035** / 67.9% vs skill blend **0.6434** / 62.4% | `evaluation_valid.md` |
| Does betting the disagreement make money? | Flat ROI **−3.3% to +0.2%**, quarter-Kelly **−5.5% to −5.8%**. Every 95% interval includes zero. Hit rate on the side the model bets is **35–38%** at average decimal odds **3.15–3.45** | `backtest_valid.md` |
| Does the in-play model beat a live Kalshi price? | Unknown. It beats the pre-fight prior (test accuracy 63% → 75%). Kalshi watches the same fight. One live bout agreed within a few cents | `inplay_eval.md`, `kalshi_trading.md` |

The backtest is longshot-heavy. A 38% hit rate at 3.15 average decimal odds would be profitable if the winners carried those odds. The realized ROI is negative, which means the dogs are the bets that miss and the winners were the shorter prices. Raising the edge threshold bets fewer, larger disagreements and does not fix this. Quarter-Kelly loses more than flat staking because it sizes up the worst disagreements.

The bot trades `p_skill` against the Kalshi ask (`prediction.mode: skill_only`, `engine.tick`). That is the probability the backtest already lost with, minus Kalshi's taker fee, the spread, and adverse selection. At a 50¢ contract the quadratic taker fee is `0.07 × price × (1 − price) = 1.75¢` before cent rounding. `min_net_edge` of 3¢ is the hurdle after that fee. Crossing the spread on top of a model that loses its disagreements is not a sizing problem.

Do not lower `min_net_edge`, raise `max_bout_fraction`, drop `min_ufc_fights`, or add mid-round attempts until a later gate in this plan passes.

## What is already right

Leave these alone. They were measured and kept, or they are the reason the bot can be experimented on at all.

- Point-in-time histories, corner symmetry, and chronological splits (`docs/leakage_audit.md`).
- Hierarchical method model. A direct three-class KO/submission/decision LightGBM was worse on 2017–2021 log loss (0.9560 vs 0.9516).
- Round hazards with a large base-rate shrink. Exact-round accuracy on the test set is 51.5%, essentially the historical method × length rate.
- Market-as-base, skill-as-residual (`models/market.py`). Putting the price in as one GBM feature scored worse than the market alone. The fitted stack is `a=1.00` on the market logit and `b=0.29` on the skill logit, fit on train-era out-of-sample priced fights, not on 2022–2023.
- Fail-closed execution: reservations before submit, no write retries, identity checks, KXUFCFIGHT only, depth cap, paused restart.

Also rejected, so this plan does not reopen them: dropping raw `f1_`/`f2_` features, a 40-trial GBM retune, isotonic calibration on the method heads, the low-history debut GBM, and an experience-boosted Elo K. The test-set blend is 0.0023 log loss worse than logistic alone; an event-date bootstrap already put that gap inside **[−0.0048, +0.0095]**. Do not retune the blend on the test era.

## Model flaws, in the order they cost probability

### 1. The bot bets the wrong probability

`prediction.mode` is `skill_only`. Cards therefore skip the market stack, the ranking nudge, and the context adjustments in `predict.py`. The trading engine stores `probability_f1` from that frozen `p_skill` and never calls `apply_market_layer`.

On the 697 priced validation fights the layers rank like this:

| Probability the product could bet | Log loss | Accuracy |
|---|---:|---:|
| Skill blend, what the bot uses | 0.6434 | 62.4% |
| Shipped stack plus veteran mix plus market-trap | 0.6075 | 66.9% |
| Vig-free market | 0.6035 | 67.9% |
| Pure stack, `sigmoid(1.00·logit(market) + 0.29·logit(skill))` | 0.6010 | 67.6% |

The pure stack's 0.0025 log-loss edge over the market is too small to bet. It is the least-bad number the repo has, and two later steps throw it away:

- `research_weight` (0.55, scaled by UFC history up to 8 fights) pulls veterans back toward skill. That is why "shipped" is worse than the market.
- `skill_only` throws the market out entirely. That is what the bot bets.

Trading change: when a contemporaneous line exists, the order probability is the pure stack, not `p_skill` and not the research-weight mix. When no line exists, the bot abstains. A skill-only number is allowed only as a fallback prior inside the in-play model, and only when no pre-fight Kalshi mid was captured.

Acceptance: on a fresh post-2023 priced slice (the current test parquet has **zero** odds), the traded probability's log loss is no worse than the vig-free line. Until that slice exists, this change is a loss-cutter, not an alpha claim.

### 2. `quality_win_rate` is not a win rate

`form_snapshot` in `features/research.py` divides quality wins by every decisive fight:

```python
quality = [f for f in decisive if f.opp_elo_pre >= bar]
quality_wins = [f for f in quality if f.result == "win"]
"quality_win_rate": len(quality_wins) / len(decisive) if decisive else None
```

A fighter who is 1–0 against elites and 10–0 against everyone else scores 1/11. A fighter who is 1–10 against elites and never fought down also scores 1/11. Fighters who have never faced an elite score 0, which the linear model can read as "bad" rather than "untested." The name and the comment describe a rate against quality opposition. The denominator is career length.

Fix: `len(quality_wins) / len(quality)` when `len(quality) >= 2`, else missing. Keep the current ratio under a different name (`quality_win_share`) only if a walk-forward says it still helps after the rate exists. Rebuild features, retrain, and compare train-era then validation log loss before touching the artifact the bot loads.

### 3. The linear model is fighting its own features

Largest standardized logistic coefficients, test report:

| Feature | Coefficient | What it is doing |
|---|---:|---|
| `diff_ko_end_rate_l5` | −0.51 | |
| `diff_dec_end_rate_l5` | −0.50 | |
| `diff_sub_end_rate_l5` | −0.35 | These three are a composition. They move together. All three negative is a collinearity artifact in a no-intercept model, not "finishes are bad." |
| `diff_losses` | +0.43 | More career losses predict a win, because losses proxy experience after win rate is in the model. |
| `diff_pre_ufc_ko_rate` and `diff_pre_ufc_sub_rate` | +0.38 | |
| `diff_pre_ufc_finish_rate` | −0.27 | Same composition problem one level down. |

This does not mean "delete the logistic." It is the better of the two base models on the test set. It means stop adding more raw rates that sum to one. Replace compositional triples with a single contrast (finish share, and KO share given a finish) before the next feature round.

### 4. In-play is trained on a different problem than it trades

`InplayModel` is an antisymmetric logistic, `C=0.03`, no intercept, no calibration. The prior coefficient is **+0.52**. Volume is counted three times (`sig_l` +0.23, `head_l` +0.24, `tot_l` +0.14). Knockdowns are **−0.05** once strikes are in the model, so "power" is not identified.

Training rows are end-of-round cumulative totals (`inplay/data.py`). Live trading calls `predict_progress` with a fractional clock and ESPN totals that are partial and often about 30 seconds behind the broadcast (`live.py`, `kalshi_trading.md`). The artifact was fit on closing-line priors through 2023. The test report and the live fallback use `p_skill`. Live, the prior is the captured Kalshi mid when one exists.

Validation calibration got worse where most live trades would fire. After round 1, ECE moved from **0.044 to 0.060** while accuracy only moved from 67.8% to 71.5%. After round 2 the probability jump is real (log loss 0.615 → 0.430). Rounds 3–4 are a few dozen five-round fights.

Trading change, before any new in-play features: live orders only on `STATUS_END_OF_ROUND` inside the existing 10–40 second window. No fractional-clock orders until a training set of mid-round snapshots exists. Recalibrate on 2022–2023 break rows and report ECE by round. The order fires only when `|p − live Kalshi mid|` clears the fee plus the spread plus a fixed 4¢ until that ECE is under the prior's ECE.

### 5. The contract is not the label

Training drops non-decisive fights. Kalshi settles a draw or no-contest at 50¢. The bot treats `P(win)` as the expected payout of a $1 binary.

If `p` is the model's decisive-win probability and `d` is the probability of a 50¢ settlement,

`E[payout] = p + d · (0.5 − p)`.

Favorites are overstated and underdogs are understated by `d · (p − 0.5)`. Look up `d` on the historical fights that match the KXUFCFIGHT rules (not a guessed rate) and subtract it inside `edge_of`. This is a small correction. It is still required before any live size increase, because the current edge is already inside a few cents.

### 6. Evaluation cannot see the era the bot trades

The test parquet has no market column. `select_k` for Elo is tested and documented, and `cmd_build_features` never calls it; `k_factor: 80` is a manual constant. `docs/trading_model_readiness.md` still says there is no in-play model. `kalshi_trading.md` says one attempt per bout; `RiskPolicy` allows 6 pre-fight, 12 live, and 3 break attempts. None of these change a probability by themselves. They make the next experiment lie.

## New features

Ship a feature only if the **pure market stack** log loss improves on the 2022–2023 priced fights, and the disagreement subset (fights where `|p − market| ≥ 0.04`) does not get worse. A skill-only accuracy bump that widens the gap to the close is a failed experiment. The September 2026 research note already showed that pattern: small accuracy gains with a worse ECE.

### Use the round file that is already in the database

Greco round rows feed the in-play model and almost nothing in the pre-fight table. Pre-fight features to add, all point-in-time, last 5 statted UFC fights:

- Cardio slope: round-3 significant-strike rate divided by round-1 rate, and the same for control time. A wrestler who fades is a different bet from a wrestler who holds pace. `avg_fight_min` does not capture this.
- Early-finish profile already has round-1 finish rates. Add early *absorption*: knockdowns and takedowns conceded in round 1, per minute.
- Power and chin, separated from volume: knockdowns landed per 100 head strikes landed, and knockdowns absorbed per 100 head strikes absorbed. The in-play coefficient on raw knockdowns says volume is drowning power.

### Stop feeding the logistic raw sums

- Opponent-adjusted `sapm` and `td15`: residual versus the opponent's pre-fight Elo, not the raw last-5 average. A striker who looks efficient against debuts is how the model fades the wrong side.
- One finish-mix contrast instead of KO rate, submission rate, and decision rate together. Same for the pre-UFC triple.

### Fix the feature that is already misnamed

The `quality_win_rate` denominator bug above. Add `quality_n` so the model can tell "untested" from "tested and lost."

### Information the closing line has and the table does not

These are the only pre-fight features with a mechanism for beating a line, and only if the observation is timestamped before the fight and, ideally, before the bet:

- Days of notice, and a replacement flag, from the circumstance parser in `scraping/context.py`. Today this nudges a prediction at card time when `market_aware` is on. It is not in the feature table and it has no walk-forward score.
- Missed weight or catchweight, with the miss in pounds.
- Weight-class change versus the fighter's previous bout. `weight_class` is stored per fight and never differenced.
- Regional opponent Elo from Sherdog opponent names. `regional._opp_elo` uses a promotion-tier regex (1350 / 1450 / 1550), so two undefeated regional records look alike. This is the DWCS hole: test-era bouts with either fighter under three UFC fights were 61.7% / 0.641 log loss, versus 67.9% / 0.618 for the rest (`trading_model_readiness.md`).

YouTube lean and headline sentiment stay off the training matrix. They are post-hoc, easy to overfit to a card, and already gated to a coin-flip band. If they are kept, score them as a frozen nudge on the next three cards and throw them out if the nudge's log loss loses to leaving the probability alone.

### Do not add these to the winner model

Odds as a GBM column, a debut GBM, another Optuna sweep, and anything whose source timestamp cannot be proven earlier than the fight. The market stack is the right place for the price.

## Trading plan

The execution layer is good enough to run the experiments. The signal is not. Changes are ordered so a later step cannot run until the earlier gate is written down.

### Phase 0 — make profit measurable

No threshold changes.

- Persist, per attempt: model probability, which layer produced it, Kalshi bid/ask/mid, fee, depth, fill price, fill count, and the ESPN state.
- On settlement, write the contract result, including 50¢ draw and no-contest. The dashboard currently reports spend. `remaining_dollars` does not add settlement cash back, which is correct for a cap and useless as a P&L.
- Closing-line value: fill price versus the last Kalshi mid before the bout starts, and versus a vig-free sportsbook close when one was captured. For in-play, fill price versus the Kalshi mid 60 seconds later.
- Uncertainty is an event-block bootstrap. The sportsbook backtest resamples bets, and fights on one card are not independent.
- Paper fills stay labeled as paper. Displayed depth is not a fill.

Gate: a scorecard script that, given a state directory, prints attempts, fills, mean CLV in cents, settlement P&L, and the event-block interval. Until that script exists, "more profit" is not a thing this repo can see.

### Phase 1 — stop betting the disagreement

- Order probability becomes the pure stack when both a model card and a line exist.
- `research_weight` stays available for the written card. It is not an input to `edge_of`.
- No line: no pre-fight order. `min_ufc_fights` stays at 1.
- `edge_of` uses expected payout after the measured draw/no-contest rate, not raw `P(win)`.
- `probability_haircut` stays 0 until Phase 0 shows the traded subset is miscalibrated. A global haircut on a biased probability just moves the bias.

Gate: on the next recorded events, mean pre-fight CLV of filled orders is ≥ 0. If it is negative, stop and go back to features. Do not "fix" a negative CLV by betting more.

### Phase 2 — bet the slow venue, not the model

The skill model does not have a measured edge over a sharp close. Kalshi can still be the slow book.

- Capture a vig-free sportsbook probability at the same time as the Kalshi book.
- A pre-fight order is allowed when the Kalshi ask is worse than that sportsbook probability by more than the taker fee, half the spread, and 2¢, and the pure stack does not disagree with the sportsbook by more than 8¢. The second check refuses a Kalshi quote that is stale because the sportsbook itself is wrong.
- This is a cross-venue lag trade. It is not "the model faded the favorite."

Gate: mean CLV against the Kalshi pre-fight close ≥ +2¢ over at least 30 filled orders and 4 events, event-block interval not entirely below zero. Thirty is small. It is a kill-switch, not a proof.

### Phase 3 — size the bets that survived

Current sizing (`bout_allowance`) splits the phase pool across every open fight, scales by `kelly / 0.10` up to 2×, caps a fight at 40% of the event budget, holds 30% back when in-play is on, and forces one contract onto any fight with an edge and nothing spent. On a small budget that last rule is a dust bet. Dust bets on negative-CLV longshots are how the Kelly rows in the backtest lose extra.

After Phase 2's gate, and only then:

- Drop the one-contract floor.
- Rank open fights by net edge and send the budget to the top two.
- Cap one fight at **15%** of the event budget. The current 40% is a ruin setting for a model whose disagreements lose.
- Leave `inplay_reserve` at 30% only if Phase 4 is enabled. Otherwise the reserve is unused cash, which is fine.

Do not move `full_slice_kelly` or `max_slice_multiple` until the 15% cap has a positive event-block P&L on paper.

### Phase 4 — in-play, at the break, with an exit

- Delete the live-round attempt family from the order policy until mid-round rows exist. Keep the break family (3 attempts, 4 seconds apart, 10–40 second window).
- Prior is the captured pre-fight Kalshi mid. `p_skill` only if that file has no row.
- Retrain the in-play logistic on ratios: significant-strike differential per minute, head share of strikes, takedown accuracy, knockdown differential per minute, control per minute. Keep the prior. Drop the triple-counted raw totals.
- Fit a calibrator on 2022–2023 only. Publish ECE by round next to accuracy.
- Add a sell. A holding sells when the live mid is above the model's fair value by more than the fee to exit. It does not sell because the position is red while the model still says the mid is cheap. Buys and sells share the bout dollar cap.

Gate: break-time `|model − Kalshi mid|` on at least 20 bouts, and paper CLV of break orders and of exits, reported separately. The October 31 check (one bout, two breaks, agreement within a few cents) is a prior, not a result. If the median absolute gap stays inside the fee, in-play stays off. Accuracy against the eventual winner is not the gate.

### Phase 5 — features that could create a residual

Build in this order, each behind the market-stack gate in the feature section:

1. `quality_win_rate` denominator, plus `quality_n`.
2. Cardio slope and knockdowns per 100 head strikes, from rounds already stored.
3. Opponent-adjusted striking and grappling rates. Compositional rate cleanup in the logistic frame.
4. Weight-class move, short notice, replacement, missed weight. All with a timestamp audit.
5. Sherdog opponent-graph Elo for fighters with fewer than three UFC bouts. Judge this slice on its own log loss. The debut GBM stays rejected unless this feature flips the low-history comparison that killed it (0.6649 vs 0.6582 on the old training-era cut).

Each step retrains from the training cutoff. No reuse of a calibration fit that predates the feature change (`lineage.py` already refuses a mismatched fingerprint).

## Sequence

| Step | Change | Ships when |
|---|---|---|
| 0 | Settlement and CLV scorecard. No order-policy change. | Script runs on a paper state dir |
| 1 | Fix `quality_win_rate`. Rebuild, walk-forward, do not promote unless validation stack log loss improves or stays inside 0.002 | Train-era and validation both reported |
| 2 | Bot uses pure stack; abstain with no line; draw adjustment in `edge_of`; break-only in-play | Phase 0 scorecard shows pre-fight CLV ≥ 0, or the change is kept as a loss-cut with size still tiny |
| 3 | Sportsbook-versus-Kalshi lag rule | ≥ +2¢ mean CLV, ≥ 30 fills, ≥ 4 events |
| 4 | Top-two fights, 15% cap, no one-contract floor | Step 3 gate held on the next events |
| 5 | In-play ratios, calibration, sell rule | Median break gap > fees, paper CLV ≥ 0 |
| 6 | Cardio, power/chin, opponent-adjusted rates, notice and weight, regional graph | Each one beats the pure stack on 2022–2023 priced fights and does not worsen the disagreement subset |

## What this plan refuses to do

- Tune `min_net_edge` below 3¢ or the spread cap above 8¢ to "get more bets on."
- Treat the in-play accuracy jump as a trading edge.
- Turn YouTube or news sentiment into a fitted coefficient.
- Retune LightGBM, the blend weight, or the method hierarchy on the published validation or test windows.
- Describe paper ROI as a return.
