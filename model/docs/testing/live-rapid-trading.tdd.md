# TDD evidence: live repricing and rapid in-fight orders

> Superseded on November 9, 2026. Mid-round buys are now limited to 3 a round, 30 seconds
> apart, behind the guards in [kalshi_trading.md](../kalshi_trading.md). This file records
> the earlier once-a-second behavior.

Source plan: none. Journeys were written for the request to reprice from live fight data and trade quickly. The working tree already held unrelated uncommitted edits, so this run did not create checkpoint commits.

## User journeys

1. As a trader, I want the in-play model to reprice a fight from the latest ESPN clock and cumulative stats, so the probability moves during the round.
2. As a trader, I want a buy when that updated price still clears fees and depth, retried about once a second while the edge lasts, with the bout budget and attempt cap still holding.
3. As a trader, I want a missing clock, a finished fight, and the final bell to keep blocking orders.

## Task report

| Task | What ran | Result | Guarantee |
|---|---|---|---|
| Live progress model | `uv run --extra trading pytest -q tests/test_inplay.py::test_live_progress_rises_as_the_clock_runs_and_swaps_corners` | RED: `AttributeError: predict_progress`. GREEN: pass | A later clock raises P(f1) for the same strike lead, and swapping corners complements the probability. Elapsed time outside `(0, scheduled)` is refused. |
| ESPN clock parser | `...::test_fight_progress_uses_the_round_clock_and_completed_breaks` | RED: `AttributeError: fight_progress`. GREEN: pass | Round 2 at 2:30 is 1.5 elapsed rounds. A break stays an integer completed round. A missing, blank, over-long, or finished observation is refused. |
| Trade from the updated price | `...::test_live_clock_updates_the_price_then_trades_once_a_second` | RED: reason was `Not in a between-rounds break`. GREEN: pass | At 4:30 of round 1 the same lead is under 60% and does not trade. At 0:30 of round 3 it is over 70% and paper-buys `1:l3`. The next tick waits; one second later it buys `1:l3:2`. Further tries stop at 12, inside the bout dollar cap. |
| One-second worker | `...::test_in_fight_checks_run_on_the_live_retry_cadence` | RED: `AttributeError: decision_interval`. GREEN: pass | With an in-play model the decision interval is 1.0 s. Without it, the interval stays 2.0 s, and `decide` sleeps on `decision_interval`. |
| Still refuse bad live state | `...::test_live_action_without_a_clock_or_after_the_final_round_does_not_trade` | RED: reason was `Not in a between-rounds break`. GREEN: pass | Live action with no clock does not order. A break after the final round does not order. |

Full suite after the change: `uv run --extra trading pytest -q` → `461 passed`.

`pytest-cov` is not installed in this project, so a numeric coverage percentage was not produced. The new parser, progress model, attempt family, and decision interval are executed by the tests above. Existing break, pre-fight, and budget tests still pass.

## Test specification

| # | What is guaranteed | Test | Type | Result |
|---|---|---|---|---|
| 1 | Later elapsed time raises the leader's win probability, and a corner swap complements it | `test_live_progress_rises_as_the_clock_runs_and_swaps_corners` | unit | PASS |
| 2 | A live clock becomes fractional elapsed rounds; a break stays a completed round | `test_fight_progress_uses_the_round_clock_and_completed_breaks` | unit | PASS |
| 3 | A cheap early price is skipped; the same stats later in the fight buy, then retry once a second up to 12 times inside the bout cap | `test_live_clock_updates_the_price_then_trades_once_a_second` | integration | PASS |
| 4 | In-fight checks run every second; pre-fight checks stay at two seconds | `test_in_fight_checks_run_on_the_live_retry_cadence` | unit | PASS |
| 5 | No clock and the final bell still place no order | `test_live_action_without_a_clock_or_after_the_final_round_does_not_trade` | integration | PASS |

## Known gaps

- The live price uses the between-rounds coefficients on partial round totals. That is an extrapolation; ESPN is often behind the broadcast. The tests prove the wiring, not that the price is profitable.
- No browser journey covers a live card. The dashboard copy was checked with the bot offline.
- Checkpoint commits were not made. The tree already contained other uncommitted edits in the same files.
