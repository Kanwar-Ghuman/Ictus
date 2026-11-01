# UFC Fight Night: Moicano vs. Nolan — 2026-10-31

Point-in-time predictions from 8731 historical fights. Educational output — NOT betting advice; the backtest shows this model does not beat the market.

Name spellings resolved against ufcstats: Ode' Osbourne -> Ode Osbourne

Prediction mode: **skill_only**. Odds, ranking nudges and social sentiment do not change these probabilities.
Historical results available through 2026-09-12.

## Renato Moicano vs. Tom Nolan — Lightweight
P(Renato Moicano wins) = 0.361  ->  pick: Tom Nolan (64%)
- research: Form: Tom Nolan holds the pre-fight-expectation-adjusted form edge (mixed vs hot over the last 5).
- research: Style record: Tom Nolan is 83% against strikers in the UFC.
- recent fights, Renato Moicano: 2026-04-04 win vs Chris Duncan (SUB); 2025-06-28 loss vs Beneil Dariush (U-DEC); 2025-01-18 loss vs Islam Makhachev (SUB)
- recent fights, Tom Nolan: 2026-06-06 win vs Fares Ziam (U-DEC); 2025-09-27 win vs Charlie Campbell (SUB); 2025-02-08 win vs Viacheslav Borshchev (U-DEC)
- independent model votes for Renato Moicano: logistic 34.7%, calibrated GBM 36.7%. Their spread is a sensitivity check, not a confidence interval.

| Pre-fight evidence | Renato Moicano | Tom Nolan |
|---|---:|---:|
| Age | 37.45 | 26.65 |
| Reach (cm) | 182.88 | 185.42 |
| UFC fights | 20.00 | 6.00 |
| Days since UFC fight | 210.00 | 147.00 |
| Last 3: sig. strikes landed/min | 2.23 | 3.69 |
| Last 3: sig. strikes absorbed/min | 3.26 | 2.84 |
| Last 5: takedowns/15 min | 1.29 | 1.13 |
| Last 5: takedown defense (fraction) | 0.33 | 0.58 |
| Last 5: control-time fraction | 0.33 | 0.18 |
| Last 5: opponent pre-fight Elo | 1751.09 | 1542.88 |

- method: Renato Moicano by KO 12% / sub 13% / dec 11%; Tom Nolan by KO 34% / sub 11% / dec 19%
- pick outcome: Tom Nolan by KO/TKO, round 1 (method 34%; round given method 44%; exact outcome 15%)
- how it ends: finish 69% (R1 27% / R2 21% / R3 12% / R4 6% / R5 4%) vs. decision 31%
- likeliest endings: Tom Nolan by decision (19%), Tom Nolan by KO/TKO, round 1 (15%), Renato Moicano by decision (11%)
- drivers (log-odds): diff_age -0.41, diff_strike_elo +0.15, diff_opp_elo_l5 +0.14, diff_career_win_pct -0.09, diff_elo +0.08

| ending | R1 | R2 | R3 | R4 | R5 | any round |
|---|---|---|---|---|---|---|
| Renato Moicano by KO/TKO | 4.1% | 3.6% | 2.1% | 1.1% | 0.9% | **11.7%** |
| Renato Moicano by submission | 3.9% | 4.0% | 2.7% | 1.5% | 1.0% | **13.1%** |
| Tom Nolan by KO/TKO | 15.0% | 9.9% | 5.0% | 2.4% | 1.8% | **34.0%** |
| Tom Nolan by submission | 4.2% | 3.1% | 1.9% | 1.0% | 0.5% | **10.7%** |
| decision (either fighter) | — | — | — | — | — | **30.5%** |

## Randy Brown vs. Jacobe Smith — Welterweight
P(Randy Brown wins) = 0.380  ->  pick: Jacobe Smith (62%)
- research: Wrestling contrast: Jacobe Smith lands 4.5 takedowns/15 into Randy Brown's 75% TDD.
- research: Form: Jacobe Smith holds the pre-fight-expectation-adjusted form edge (cold vs hot over the last 5).
- research: Style record: Jacobe Smith is 100% against strikers in the UFC.
- research: Common opponents (1): Jacobe Smith's record against them is better.
- recent fights, Randy Brown: 2026-04-11 loss vs Kevin Holland (U-DEC); 2025-11-08 loss vs Gabriel Bonfim (KO/TKO); 2025-04-26 win vs Nicolas Dalby (KO/TKO)
- recent fights, Jacobe Smith: 2026-02-21 win vs Josiah Harrell (KO/TKO); 2025-06-28 win vs Niko Price (SUB); 2025-01-11 win vs Preston Parsons (KO/TKO)
- independent model votes for Randy Brown: logistic 35.3%, calibrated GBM 39.1%. Their spread is a sensitivity check, not a confidence interval.

| Pre-fight evidence | Randy Brown | Jacobe Smith |
|---|---:|---:|
| Age | 36.31 | 30.79 |
| Reach (cm) | 198.12 | 182.88 |
| UFC fights | 22.00 | 3.00 |
| Days since UFC fight | 203.00 | 252.00 |
| Last 3: sig. strikes landed/min | 4.70 | 6.85 |
| Last 3: sig. strikes absorbed/min | 4.13 | 3.61 |
| Last 5: takedowns/15 min | 0.51 | 4.52 |
| Last 5: takedown defense (fraction) | 0.75 | 1.00 |
| Last 5: control-time fraction | 0.09 | 0.47 |
| Last 5: opponent pre-fight Elo | 1654.61 | 1505.07 |

- method: Randy Brown by KO 13% / sub 7% / dec 17%; Jacobe Smith by KO 24% / sub 13% / dec 25%
- pick outcome: Jacobe Smith by decision (25%)
- how it ends: finish 58% (R1 30% / R2 18% / R3 9%) vs. decision 42%
- likeliest endings: Jacobe Smith by decision (25%), Randy Brown by decision (17%), Jacobe Smith by KO/TKO, round 1 (14%)
- drivers (log-odds): diff_style_reach_striker +0.22, diff_age -0.22, diff_strike_elo +0.20, diff_career_win_pct -0.10, diff_opp_elo_l5 +0.09

| ending | R1 | R2 | R3 | any round |
|---|---|---|---|---|
| Randy Brown by KO/TKO | 6.4% | 4.5% | 2.5% | **13.4%** |
| Randy Brown by submission | 3.2% | 2.5% | 1.5% | **7.2%** |
| Jacobe Smith by KO/TKO | 13.5% | 6.9% | 3.2% | **23.6%** |
| Jacobe Smith by submission | 7.3% | 4.1% | 2.0% | **13.4%** |
| decision (either fighter) | — | — | — | **42.4%** |

## Ode Osbourne vs. Cody Durden — Flyweight
P(Ode Osbourne wins) = 0.448  ->  pick: Cody Durden (55%; close fight)
- research: Wrestling contrast: Cody Durden lands 3.3 takedowns/15 into Ode Osbourne's 66% TDD.
- research: Last fights: Ode Osbourne lost last time out; Cody Durden lost last time out.
- research: Style record: Cody Durden is 40% against strikers in the UFC.
- research: Common opponents (2): Cody Durden's record against them is better.
- recent fights, Ode Osbourne: 2026-02-21 loss vs Alibi Idiris (U-DEC); 2025-08-09 loss vs Steve Erceg (U-DEC); 2025-04-05 win vs Luis Gurule (KO/TKO)
- recent fights, Cody Durden: 2026-07-11 loss vs Alessandro Costa (SUB); 2026-04-25 win vs Jafel Filho (U-DEC); 2026-03-07 loss vs Nyamjargal Tumendemberel (U-DEC)
- independent model votes for Ode Osbourne: logistic 39.6%, calibrated GBM 47.0%. Their spread is a sensitivity check, not a confidence interval.

| Pre-fight evidence | Ode Osbourne | Cody Durden |
|---|---:|---:|
| Age | 34.81 | 35.59 |
| Reach (cm) | 185.42 | 170.18 |
| UFC fights | 13.00 | 17.00 |
| Days since UFC fight | 252.00 | 112.00 |
| Last 3: sig. strikes landed/min | 2.30 | 1.88 |
| Last 3: sig. strikes absorbed/min | 1.68 | 1.85 |
| Last 5: takedowns/15 min | 0.53 | 3.25 |
| Last 5: takedown defense (fraction) | 0.66 | 0.25 |
| Last 5: control-time fraction | 0.06 | 0.24 |
| Last 5: opponent pre-fight Elo | 1506.72 | 1521.63 |

- method: Ode Osbourne by KO 8% / sub 17% / dec 20%; Cody Durden by KO 8% / sub 17% / dec 30%
- pick outcome: Cody Durden by decision (30%)
- how it ends: finish 50% (R1 25% / R2 17% / R3 8%) vs. decision 50%
- likeliest endings: Cody Durden by decision (30%), Ode Osbourne by decision (20%), Ode Osbourne by submission, round 1 (9%)
- drivers (log-odds): diff_strike_elo +0.16, diff_grapple_elo -0.08, diff_career_fights_24m -0.07, f1_grapple_elo -0.07, diff_style_reach_striker +0.07

| ending | R1 | R2 | R3 | any round |
|---|---|---|---|---|
| Ode Osbourne by KO/TKO | 4.9% | 2.5% | 1.0% | **8.4%** |
| Ode Osbourne by submission | 9.1% | 5.2% | 2.2% | **16.5%** |
| Cody Durden by KO/TKO | 3.7% | 2.8% | 1.6% | **8.1%** |
| Cody Durden by submission | 7.5% | 6.2% | 3.5% | **17.2%** |
| decision (either fighter) | — | — | — | **49.7%** |

## Yana Santos vs. Luana Santos — Women's Bantamweight
P(Yana Santos wins) = 0.228  ->  pick: Luana Santos (77%)
- research: Wrestling contrast: Luana Santos lands 2.3 takedowns/15 into Yana Santos's 53% TDD.
- research: Last fights: Yana Santos won last time out; Luana Santos won last time out.
- research: Style record: Luana Santos is 83% against strikers in the UFC.
- research: Common opponents (1): Luana Santos's record against them is better.
- recent fights, Yana Santos: 2025-10-04 win vs Macy Chiasson (U-DEC); 2025-05-03 win vs Miesha Tate (U-DEC); 2024-08-10 win vs Chelsea Chandler (U-DEC)
- recent fights, Luana Santos: 2026-06-20 win vs Karol Rosa (U-DEC); 2025-12-13 win vs Melissa Croden (U-DEC); 2025-05-17 win vs Tainara Lisboa (SUB)
- independent model votes for Yana Santos: logistic 23.2%, calibrated GBM 22.6%. Their spread is a sensitivity check, not a confidence interval.

| Pre-fight evidence | Yana Santos | Luana Santos |
|---|---:|---:|
| Age | 36.97 | 26.54 |
| Reach (cm) | 172.72 | 170.18 |
| UFC fights | 12.00 | 7.00 |
| Days since UFC fight | 392.00 | 133.00 |
| Last 3: sig. strikes landed/min | 5.00 | 0.90 |
| Last 3: sig. strikes absorbed/min | 3.33 | 0.88 |
| Last 5: takedowns/15 min | 0.00 | 2.31 |
| Last 5: takedown defense (fraction) | 0.53 | 1.00 |
| Last 5: control-time fraction | 0.10 | 0.59 |
| Last 5: opponent pre-fight Elo | 1574.43 | 1540.91 |

- method: Yana Santos by KO 4% / sub 2% / dec 17%; Luana Santos by KO 14% / sub 23% / dec 40%
- pick outcome: Luana Santos by decision (40%)
- how it ends: finish 42% (R1 23% / R2 13% / R3 6%) vs. decision 58%
- likeliest endings: Luana Santos by decision (40%), Yana Santos by decision (17%), Luana Santos by submission, round 1 (13%)
- drivers (log-odds): diff_age -0.41, diff_strike_elo +0.19, diff_career_win_pct -0.10, diff_td15_l5 -0.09, diff_grapple_elo -0.07

| ending | R1 | R2 | R3 | any round |
|---|---|---|---|---|
| Yana Santos by KO/TKO | 1.6% | 1.2% | 0.7% | **3.5%** |
| Yana Santos by submission | 0.8% | 0.6% | 0.4% | **1.8%** |
| Luana Santos by KO/TKO | 7.6% | 4.1% | 1.8% | **13.5%** |
| Luana Santos by submission | 12.6% | 7.3% | 3.3% | **23.2%** |
| decision (either fighter) | — | — | — | **58.0%** |

## Jean-Paul Lebosnoyani vs. Farman Hasanov — Welterweight
P(Jean-Paul Lebosnoyani wins) = 0.495  ->  pick: Farman Hasanov (50%; close fight)
- research: Wrestling contrast: Farman Hasanov lands 17.0 takedowns/15 into Jean-Paul Lebosnoyani's 100% TDD.
- research: Form: Jean-Paul Lebosnoyani holds the pre-fight-expectation-adjusted form edge (hot vs hot over the last 5).
- recent fights, Jean-Paul Lebosnoyani: 2026-07-18 win vs Seokhyeon Ko (U-DEC); 2026-02-21 win vs Phil Rowe (S-DEC); 2025-09-02 win vs Jack Congdon (KO/TKO)
- recent fights, Farman Hasanov: 2026-06-27 win vs Eric Nolan (U-DEC); 2025-11-21 win vs Abdurakhmon Fazilov (KO/TKO); 2025-06-20 win vs Marc-Ari William Lewis (KO/TKO)
- independent model votes for Jean-Paul Lebosnoyani: logistic 48.4%, calibrated GBM 50.0%. Their spread is a sensitivity check, not a confidence interval.

| Pre-fight evidence | Jean-Paul Lebosnoyani | Farman Hasanov |
|---|---:|---:|
| Age | 27.76 | 31.25 |
| Reach (cm) | 182.88 | unavailable |
| UFC fights | 2.00 | 1.00 |
| Days since UFC fight | 105.00 | 126.00 |
| Last 3: sig. strikes landed/min | 3.93 | 1.40 |
| Last 3: sig. strikes absorbed/min | 4.00 | 1.00 |
| Last 5: takedowns/15 min | 3.00 | 17.00 |
| Last 5: takedown defense (fraction) | 1.00 | unavailable |
| Last 5: control-time fraction | 0.25 | 0.75 |
| Last 5: opponent pre-fight Elo | 1559.04 | 1460.00 |

- method: Jean-Paul Lebosnoyani by KO 13% / sub 17% / dec 19%; Farman Hasanov by KO 19% / sub 5% / dec 26%
- pick outcome: Farman Hasanov by decision (26%)
- how it ends: finish 55% (R1 28% / R2 17% / R3 9%) vs. decision 45%
- likeliest endings: Farman Hasanov by decision (26%), Jean-Paul Lebosnoyani by decision (19%), Farman Hasanov by KO/TKO, round 1 (10%)
- drivers (log-odds): f2_reach_cm +0.38, f1_reach_cm +0.30, diff_height_cm -0.17, diff_age +0.14, diff_strike_elo -0.13

| ending | R1 | R2 | R3 | any round |
|---|---|---|---|---|
| Jean-Paul Lebosnoyani by KO/TKO | 6.6% | 4.2% | 2.3% | **13.1%** |
| Jean-Paul Lebosnoyani by submission | 8.4% | 5.7% | 3.2% | **17.3%** |
| Farman Hasanov by KO/TKO | 10.3% | 5.9% | 3.0% | **19.2%** |
| Farman Hasanov by submission | 2.8% | 1.7% | 0.9% | **5.4%** |
| decision (either fighter) | — | — | — | **44.9%** |

---
*Simulation/educational project. No betting advice. The market knows more than this model.*