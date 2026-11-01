# Model evidence and live trading readiness

Reviewed October 31, 2026. These are measured limitations of the local Ictus
snapshot, not a forecast of future returns. No trading strategy can guarantee
profit or eliminate the possibility of losing an event budget.

## What the existing model measures

The winner model is a **pre-fight** model. It combines logistic regression with
calibrated LightGBM predictions using fighter histories from before the card.
`prediction.mode` currently selects `skill_only`; the trading integration must
use frozen `p_skill` with its original fighter orientation and event identity.
Selecting a winner for every bout does not make every bout a trade opportunity.

The local feature table contains 8,731 decisive fights through **September 12,
2026**, with 373 stored columns. The current artifact uses 363 model inputs,
five LightGBM seeds, 30% logistic weight, logistic C=0.03, and a six-year recency
half-life. The optional debut specialist is disabled. Its calibration/blend
cutoff is December 31, 2021, and its historical feature fingerprint matches the
current table. Prediction refits the base estimators on pre-card history; that
does not turn the artifact into an in-play model.

Existing reports, generated September 17, 2026, contain these results:

| Evaluation | Fights | Accuracy | Log loss | Brier | ECE |
|---|---:|---:|---:|---:|---:|
| Skill blend, 2022–2023 validation | 1,010 | 61.68% | 0.6469 | 0.2280 | 0.0295 |
| Skill blend, priced validation subset | 697 | 62.41% | 0.6434 | 0.2264 | 0.0327 |
| Vig-free market, same validation subset | 697 | 67.93% | 0.6035 | 0.2084 | 0.0475 |
| Skill blend, 2024–September 12, 2026 test | 1,414 | 65.21% | 0.6282 | 0.2189 | 0.0318 |
| Logistic model, same test fights | 1,414 | 65.35% | 0.6259 | 0.2180 | 0.0283 |

Lower log loss, Brier, and ECE are better. Market probabilities are absent from
**all 1,414 test rows**. The test result therefore does not demonstrate a price
advantage, and the validation market outperforms the skill model on proper
probability scores. Small aggregate ECE is not a confidence interval for an
individual fight, and does not establish calibration of trading-selected bets.

A diagnostic recomputation from the saved test predictions gives 61.71%
accuracy / 0.64118 log loss for the 619 bouts where either fighter had fewer
than three UFC fights, versus 67.92% / 0.61814 for 795 other bouts. The blend's
log loss exceeds logistic regression by 0.00234; an event-date bootstrap
(10,000 samples, seed 42) gives a 95% difference interval of
**[-0.00484, +0.00951]**. These exploratory diagnostics do not support changing
the production blend to claim an established gain. They also consume the
existing test set as research data; future selection needs new held-out events.

Sources in this repository: [validation report](../reports/evaluation_valid.md),
[test report](../reports/evaluation_test.md), and their saved prediction
parquets. These legacy reports are retained, not regenerated or newly certified
by this change.

## What the betting evidence says

The existing [2022–2023 paper backtest](../reports/backtest_valid.md) uses
best-available sportsbook closing prices, not Kalshi fills:

| Strategy | Reported ROI across tested edge thresholds | Interpretation |
|---|---|---|
| Flat stake | -3.3% to +0.2% | Every reported 95% interval includes zero |
| Quarter Kelly | -5.8% to -5.5% | Losses in all tested settings; every interval includes zero |

Those prices can be better than any one executable venue's prices. The
backtest lacks Kalshi fees, order-book depth, spread crossings, queue position,
partial fills, order latency, market suspensions, and feed delays. Its bootstrap
resamples individual bets rather than event blocks. Its quoted edge is model
disagreement with a closing price, not independently measured closing-line
value. It is not evidence for profitable Kalshi trading.

## Why trading must stop when a fight starts

The existing live gateway supplies event status, round, clock, results, and
string-valued ESPN statistics. There is **no trained and independently validated
in-play probability model** in the repository and no historical timestamped
Kalshi order-book/fill replay dataset. A new connection to a live feed does not
make the existing pre-fight probability conditional on the action in the cage.

Accordingly, frozen pre-fight probabilities may only be used while the matched
bout is still scheduled. `in_progress`, final/unknown states, mismatched
identities, stale or unavailable source data, and unsupported markets must
prevent new model-driven orders. Live updates are useful now for stopping
trading, identifying completed bouts, recording evidence, and monitoring an
event. They are not evidence of a profitable live signal.

Use the feed's source observation time separately from the gateway's receipt
time. A newly delivered copy of stale data is still stale. The ESPN parser now
leaves an absent source timestamp unknown, instead of substituting the local
time; unknown freshness must block trading. Collection cadence is not a measured
end-to-end latency guarantee. A broadcast or public feed can lag venue price changes.

An event budget is a maximum authorized risk/spend, not a requirement to use
the full amount. Abstaining on every fight is a valid outcome. Include fees and
open-order reservations in sizing, and do not reuse apparent cash from an
unconfirmed cancellation or unresolved fill.

## Evaluation and tuning provenance

New research evaluation now requires:

1. Calibration/blend and reusable hyperparameter cutoffs no later than the
   configured research training cutoff, for both validation and test reports.
2. A supported historical feature fingerprint matching the data being scored.
3. An explicit original tuning cutoff for reused parameters. Training refuses
   to reuse parameters tuned after the requested cutoff.

The current local artifact has `params_reused=true` but predates the recorded
original hyperparameter cutoff. Its original tuning provenance cannot be
reconstructed from its calibration date. It remains usable by the existing
card prediction path, but a new research evaluation or parameter-reuse run
will refuse it with instructions to train without `--reuse-params`. The saved
scores above are historical reported measurements, not newly verified holdout
claims. No model artifact, frozen prediction, or historical report was replaced
as part of adding this guard.

For new research, preserve the current artifact and frozen card predictions,
then tune from scratch through the configured training boundary. Do not
overwrite a research artifact with a production fit and then describe its
calibration as held out. Train-era out-of-sample calibration scores are fit
diagnostics because the calibrator itself sees those labels. Independent later
events must evaluate the whole selected model and trading policy.

## Highest-value next evidence

1. Record immutable source snapshots, receipt times, source timestamps, exact
   fight/market mappings, Kalshi book snapshots/deltas, and order/fill events.
   Preserve sequence gaps, outages, corrections, and suspensions rather than
   silently filling them with future values.
2. Build as-of in-play examples at defined round/time horizons. Labels may
   use the eventual result, but inputs must contain only information available
   at each simulated order time. Split by whole event date, keeping every
   snapshot of a fight in one fold.
3. Compare a simple in-play baseline, frozen pre-fight model, contemporaneous
   market, and candidate model on later events with the same timestamp and
   liquidity filters. Report probability scores, calibration by round/history,
   confidence intervals, and performance of the selected trading subset.
4. Replay actual execution conditions with fees, latency, depth, partial fills,
   cancellation races, and event-level exposure. Report net P&L, drawdown,
   coverage, event-block uncertainty, and sensitivity to worse fills.
5. Freeze the strategy before a forward paper-trading period. Promote an
   in-play artifact only after its whole pipeline passes independent evidence
   checks. A favorable backtest still cannot promise profits on future events.

## Addendum (October 31, 2026): between-rounds model

A between-rounds model now exists (`src/octagon/inplay/`, report in
[reports/inplay_eval.md](../reports/inplay_eval.md)). It conditions on the
pre-fight prior and ufcstats cumulative round totals that ESPN also reports
live, and is evaluated by whole-event date splits. It predicts winners far
better than the prior alone, which is expected and is **not** evidence of a
trading edge: Kalshi's in-play price observes the same fight, faster. No
historical in-play Kalshi prices exist here. On the first live comparison
(one bout, two breaks) model and market agreed within a few cents. The
remaining requirements above still apply: record break-time prices across
events, paper-trade the frozen policy forward, and measure net results before
using real money.
