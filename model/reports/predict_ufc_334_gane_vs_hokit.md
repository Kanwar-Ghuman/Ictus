# UFC 334: Gane vs. Hokit — 2026-11-14

Point-in-time predictions from 8731 historical fights. Educational output — NOT betting advice; the backtest shows this model does not beat the market.

Name spellings resolved against ufcstats: Uroš Medić -> Uros Medic; César Almeida -> Cesar Almeida; Juan Díaz -> Juan Diaz

Prediction mode: **skill_only**. Odds, ranking nudges and social sentiment do not change these probabilities.
Historical results available through 2026-09-12.

## Ciryl Gane vs. Josh Hokit — Heavyweight
P(Ciryl Gane wins) = 0.608  ->  pick: Ciryl Gane (61%)
- research: Style: both profile as strikers — a same-look fight.
- research: Pace: Josh Hokit is the volume striker (10.3 vs 6.6 SLpM).
- research: Form: Josh Hokit holds the pre-fight-expectation-adjusted form edge (hot vs hot over the last 5).
- research: Style record: Ciryl Gane is 82% against strikers in the UFC.
- research: Common opponents: 1 shared names on the record.
- recent fights, Ciryl Gane: 2026-06-14 win vs Alex Pereira (KO/TKO); 2025-10-25 nc vs Tom Aspinall (Could Not Continue); 2024-12-07 win vs Alexander Volkov (S-DEC)
- recent fights, Josh Hokit: 2026-06-14 win vs Derrick Lewis (KO/TKO); 2026-04-11 win vs Curtis Blaydes (U-DEC); 2026-01-24 win vs Denzel Freeman (KO/TKO)
- independent model votes for Ciryl Gane: logistic 63.3%, calibrated GBM 60.2%. Their spread is a sensitivity check, not a confidence interval.

| Pre-fight evidence | Ciryl Gane | Josh Hokit |
|---|---:|---:|
| Age | 36.59 | 29.00 |
| Reach (cm) | 205.74 | 185.42 |
| UFC fights | 14.00 | 4.00 |
| Days since UFC fight | 153.00 | 153.00 |
| Last 3: sig. strikes landed/min | 4.88 | 10.30 |
| Last 3: sig. strikes absorbed/min | 3.00 | 6.21 |
| Last 5: takedowns/15 min | 0.81 | 1.50 |
| Last 5: takedown defense (fraction) | 0.38 | 0.78 |
| Last 5: control-time fraction | 0.11 | 0.28 |
| Last 5: opponent pre-fight Elo | 1835.75 | 1623.15 |

- skill-only research model P(Ciryl Gane) = 0.608; vig-free market = 0.657 (gap -0.049). Market shown for comparison only.
- method: Ciryl Gane by KO 34% / sub 5% / dec 22%; Josh Hokit by KO 25% / sub 3% / dec 11%
- pick outcome: Ciryl Gane by KO/TKO, round 1 (method 34%; round given method 35%; exact outcome 12%)
- how it ends: finish 67% (R1 26% / R2 20% / R3 11% / R4 6% / R5 5%) vs. decision 33%
- likeliest endings: Ciryl Gane by decision (22%), Ciryl Gane by KO/TKO, round 1 (12%), Josh Hokit by decision (11%)
- drivers (log-odds): diff_strike_elo +0.27, diff_style_reach_striker +0.21, diff_age -0.19, diff_elo +0.13, diff_opp_elo_l5 +0.13

| ending | R1 | R2 | R3 | R4 | R5 | any round |
|---|---|---|---|---|---|---|
| Ciryl Gane by KO/TKO | 11.7% | 10.3% | 5.9% | 3.1% | 2.6% | **33.7%** |
| Ciryl Gane by submission | 1.6% | 1.7% | 1.1% | 0.6% | 0.4% | **5.5%** |
| Josh Hokit by KO/TKO | 10.9% | 6.7% | 3.7% | 1.9% | 1.5% | **24.6%** |
| Josh Hokit by submission | 1.4% | 0.9% | 0.6% | 0.3% | 0.2% | **3.4%** |
| decision (either fighter) | — | — | — | — | — | **32.7%** |

## Kayla Harrison vs. Amanda Nunes — Women's Bantamweight
P(Kayla Harrison wins) = 0.579  ->  pick: Kayla Harrison (58%; close fight)
- research: Wrestling contrast: Kayla Harrison lands 2.8 takedowns/15 into Amanda Nunes's 89% TDD.
- research: Form: Kayla Harrison holds the pre-fight-expectation-adjusted form edge (hot vs mixed over the last 5).
- research: Common opponents (2): Kayla Harrison's record against them is better.
- recent fights, Kayla Harrison: 2025-06-07 win vs Julianna Pena (SUB); 2024-10-05 win vs Ketlen Vieira (U-DEC); 2024-04-13 win vs Holly Holm (SUB)
- recent fights, Amanda Nunes: 2023-06-10 win vs Irene Aldana (U-DEC); 2022-07-30 win vs Julianna Pena (U-DEC); 2021-12-11 loss vs Julianna Pena (SUB)
- independent model votes for Kayla Harrison: logistic 51.6%, calibrated GBM 59.4%. Their spread is a sensitivity check, not a confidence interval.

| Pre-fight evidence | Kayla Harrison | Amanda Nunes |
|---|---:|---:|
| Age | 36.37 | 38.46 |
| Reach (cm) | 167.64 | 175.26 |
| UFC fights | 3.00 | 18.00 |
| Days since UFC fight | 525.00 | 1253.00 |
| Last 3: sig. strikes landed/min | 4.29 | 4.67 |
| Last 3: sig. strikes absorbed/min | 1.10 | 3.08 |
| Last 5: takedowns/15 min | 2.84 | 3.33 |
| Last 5: takedown defense (fraction) | 1.00 | 0.89 |
| Last 5: control-time fraction | 0.59 | 0.36 |
| Last 5: opponent pre-fight Elo | 1668.86 | 1612.30 |

- skill-only research model P(Kayla Harrison) = 0.579; vig-free market = 0.632 (gap -0.054). Market shown for comparison only.
- method: Kayla Harrison by KO 13% / sub 23% / dec 21%; Amanda Nunes by KO 9% / sub 8% / dec 25%
- pick outcome: Kayla Harrison by submission, round 1 (method 23%; round given method 31%; exact outcome 7%)
- how it ends: finish 53% (R1 17% / R2 15% / R3 10% / R4 6% / R5 5%) vs. decision 47%
- likeliest endings: Amanda Nunes by decision (25%), Kayla Harrison by decision (21%), Kayla Harrison by submission, round 1 (7%)
- drivers (log-odds): diff_strike_elo -0.31, diff_grapple_elo -0.14, diff_elo -0.13, diff_opp_elo_l5 +0.11, diff_age +0.09

| ending | R1 | R2 | R3 | R4 | R5 | any round |
|---|---|---|---|---|---|---|
| Kayla Harrison by KO/TKO | 4.7% | 3.8% | 2.2% | 1.2% | 1.0% | **13.0%** |
| Kayla Harrison by submission | 7.3% | 6.8% | 4.7% | 2.6% | 1.9% | **23.4%** |
| Amanda Nunes by KO/TKO | 3.0% | 2.5% | 1.6% | 0.9% | 1.0% | **9.0%** |
| Amanda Nunes by submission | 2.2% | 2.1% | 1.6% | 1.0% | 0.9% | **7.9%** |
| decision (either fighter) | — | — | — | — | — | **46.7%** |

## Caio Borralho vs. Yousri Belgaroui — Middleweight
P(Caio Borralho wins) = 0.492  ->  pick: Yousri Belgaroui (51%; close fight)
- research: Style: both profile as strikers — a same-look fight.
- research: Pace: Yousri Belgaroui is the volume striker (8.3 vs 4.2 SLpM).
- research: Form: Yousri Belgaroui holds the pre-fight-expectation-adjusted form edge (hot vs hot over the last 5).
- research: Style record: Caio Borralho is 86% against strikers in the UFC.
- recent fights, Caio Borralho: 2026-03-07 win vs Reinier de Ridder (U-DEC); 2025-09-06 loss vs Nassourdine Imavov (U-DEC); 2024-08-24 win vs Jared Cannonier (U-DEC)
- recent fights, Yousri Belgaroui: 2026-09-12 win vs Djorden Santos (KO/TKO); 2026-03-28 win vs Mansur Abdul-Malik (KO/TKO); 2025-10-18 win vs Azamat Bekoev (KO/TKO)
- independent model votes for Caio Borralho: logistic 45.8%, calibrated GBM 50.0%. Their spread is a sensitivity check, not a confidence interval.

| Pre-fight evidence | Caio Borralho | Yousri Belgaroui |
|---|---:|---:|
| Age | 33.83 | 34.45 |
| Reach (cm) | 190.50 | 200.66 |
| UFC fights | 9.00 | 3.00 |
| Days since UFC fight | 252.00 | 63.00 |
| Last 3: sig. strikes landed/min | 4.25 | 8.35 |
| Last 3: sig. strikes absorbed/min | 3.37 | 1.93 |
| Last 5: takedowns/15 min | 0.17 | 0.52 |
| Last 5: takedown defense (fraction) | 0.86 | 0.56 |
| Last 5: control-time fraction | 0.10 | 0.06 |
| Last 5: opponent pre-fight Elo | 1664.40 | 1548.67 |

- skill-only research model P(Caio Borralho) = 0.492; vig-free market = 0.592 (gap -0.101). Market shown for comparison only.
- method: Caio Borralho by KO 14% / sub 5% / dec 30%; Yousri Belgaroui by KO 22% / sub 3% / dec 25%
- pick outcome: Yousri Belgaroui by decision (25%)
- how it ends: finish 45% (R1 23% / R2 14% / R3 8%) vs. decision 55%
- likeliest endings: Caio Borralho by decision (30%), Yousri Belgaroui by decision (25%), Yousri Belgaroui by KO/TKO, round 1 (12%)
- drivers (log-odds): diff_opp_elo_l5 +0.15, diff_elo +0.14, diff_pre_ufc_major_org_share -0.13, diff_strike_elo -0.11, diff_age +0.10

| ending | R1 | R2 | R3 | any round |
|---|---|---|---|---|
| Caio Borralho by KO/TKO | 6.8% | 4.6% | 2.4% | **13.8%** |
| Caio Borralho by submission | 2.4% | 1.7% | 0.9% | **5.0%** |
| Yousri Belgaroui by KO/TKO | 11.7% | 6.7% | 4.0% | **22.3%** |
| Yousri Belgaroui by submission | 1.7% | 1.1% | 0.7% | **3.5%** |
| decision (either fighter) | — | — | — | **55.4%** |

## Uros Medic vs. Kevin Holland — Welterweight
P(Uros Medic wins) = 0.381  ->  pick: Kevin Holland (62%)
- research: Style: both profile as strikers — a same-look fight.
- research: Pace: Uros Medic is the volume striker (8.1 vs 4.3 SLpM).
- research: Form: Uros Medic holds the pre-fight-expectation-adjusted form edge (hot vs hot over the last 5).
- research: Style record: Uros Medic is 80% against strikers in the UFC.
- research: Common opponents (2): Uros Medic's record against them is better.
- recent fights, Uros Medic: 2026-08-01 win vs Daniel Rodriguez (KO/TKO); 2026-02-21 win vs Geoff Neal (KO/TKO); 2025-11-08 win vs Muslim Salikhov (KO/TKO)
- recent fights, Kevin Holland: 2026-04-11 win vs Randy Brown (U-DEC); 2025-10-18 loss vs Mike Malott (U-DEC); 2025-07-19 loss vs Daniel Rodriguez (U-DEC)
- independent model votes for Uros Medic: logistic 28.3%, calibrated GBM 40.6%. Their spread is a sensitivity check, not a confidence interval.

| Pre-fight evidence | Uros Medic | Kevin Holland |
|---|---:|---:|
| Age | 33.56 | 34.02 |
| Reach (cm) | 180.34 | 205.74 |
| UFC fights | 11.00 | 29.00 |
| Days since UFC fight | 105.00 | 217.00 |
| Last 3: sig. strikes landed/min | 10.12 | 4.22 |
| Last 3: sig. strikes absorbed/min | 2.09 | 3.82 |
| Last 5: takedowns/15 min | 0.00 | 0.68 |
| Last 5: takedown defense (fraction) | unavailable | 0.80 |
| Last 5: control-time fraction | 0.04 | 0.12 |
| Last 5: opponent pre-fight Elo | 1605.02 | 1694.68 |

- skill-only research model P(Uros Medic) = 0.381; vig-free market = 0.574 (gap -0.193). Market shown for comparison only.
- method: Uros Medic by KO 22% / sub 4% / dec 11%; Kevin Holland by KO 22% / sub 21% / dec 20%
- pick outcome: Kevin Holland by KO/TKO, round 1 (method 22%; round given method 54%; exact outcome 12%)
- how it ends: finish 69% (R1 38% / R2 21% / R3 10%) vs. decision 31%
- likeliest endings: Kevin Holland by decision (20%), Uros Medic by KO/TKO, round 1 (13%), Kevin Holland by KO/TKO, round 1 (12%)
- drivers (log-odds): diff_strike_elo -0.31, diff_style_reach_striker -0.27, diff_opp_elo_l5 -0.11, diff_reach_cm -0.11, diff_elo +0.10

| ending | R1 | R2 | R3 | any round |
|---|---|---|---|---|
| Uros Medic by KO/TKO | 13.1% | 6.3% | 3.0% | **22.3%** |
| Uros Medic by submission | 2.4% | 1.3% | 0.6% | **4.3%** |
| Kevin Holland by KO/TKO | 11.7% | 6.9% | 3.0% | **21.6%** |
| Kevin Holland by submission | 10.7% | 6.9% | 3.1% | **20.7%** |
| decision (either fighter) | — | — | — | **31.1%** |

## Bilal Hasan vs. Luis Gurule — Flyweight
P(Bilal Hasan wins) = 0.666  ->  pick: Bilal Hasan (67%)
- research: Wrestling contrast: Bilal Hasan lands 2.0 takedowns/15 into Luis Gurule's 73% TDD.
- research: Form: Bilal Hasan holds the pre-fight-expectation-adjusted form edge (hot vs cold over the last 5).
- recent fights, Bilal Hasan: 2026-08-29 win vs Nilson Rojas (KO/TKO); 2025-12-20 win vs Renaldy Manse (KO/TKO); 2025-06-06 win vs Jason Eastman (KO/TKO)
- recent fights, Luis Gurule: 2026-05-30 loss vs Rei Tsuruya (SUB); 2026-05-16 win vs Daniel Barez (U-DEC); 2026-02-21 loss vs Alden Coria (U-DEC)
- independent model votes for Bilal Hasan: logistic 84.1%, calibrated GBM 62.2%. Their spread is a sensitivity check, not a confidence interval.

| Pre-fight evidence | Bilal Hasan | Luis Gurule |
|---|---:|---:|
| Age | 25.33 | 32.99 |
| Reach (cm) | unavailable | 162.56 |
| UFC fights | 1.00 | 5.00 |
| Days since UFC fight | 77.00 | 168.00 |
| Last 3: sig. strikes landed/min | 7.10 | 6.00 |
| Last 3: sig. strikes absorbed/min | 4.42 | 6.27 |
| Last 5: takedowns/15 min | 2.01 | 0.81 |
| Last 5: takedown defense (fraction) | unavailable | 0.73 |
| Last 5: control-time fraction | 0.14 | 0.12 |
| Last 5: opponent pre-fight Elo | 1500.00 | 1494.45 |

- skill-only research model P(Bilal Hasan) = 0.666; vig-free market = 0.872 (gap -0.206). Market shown for comparison only.
- method: Bilal Hasan by KO 24% / sub 11% / dec 32%; Luis Gurule by KO 7% / sub 8% / dec 19%
- pick outcome: Bilal Hasan by decision (32%)
- how it ends: finish 49% (R1 26% / R2 15% / R3 8%) vs. decision 51%
- likeliest endings: Bilal Hasan by decision (32%), Luis Gurule by decision (19%), Bilal Hasan by KO/TKO, round 1 (13%)
- drivers (log-odds): f2_reach_cm -0.36, diff_height_cm +0.27, diff_strike_elo +0.25, f1_reach_cm -0.25, diff_age +0.18

| ending | R1 | R2 | R3 | any round |
|---|---|---|---|---|
| Bilal Hasan by KO/TKO | 13.3% | 7.3% | 3.7% | **24.3%** |
| Bilal Hasan by submission | 5.6% | 3.3% | 1.8% | **10.7%** |
| Luis Gurule by KO/TKO | 3.3% | 2.2% | 1.0% | **6.6%** |
| Luis Gurule by submission | 3.7% | 2.7% | 1.3% | **7.7%** |
| decision (either fighter) | — | — | — | **50.8%** |

## Stephen Thompson vs. Charles Radtke — Welterweight
P(Stephen Thompson wins) = 0.373  ->  pick: Charles Radtke (63%)
- research: Wrestling contrast: Charles Radtke lands 2.6 takedowns/15 into Stephen Thompson's 54% TDD.
- research: Form: Charles Radtke holds the pre-fight-expectation-adjusted form edge (cold vs mixed over the last 5).
- research: Style record: Charles Radtke is 71% against strikers in the UFC.
- recent fights, Stephen Thompson: 2025-07-12 loss vs Gabriel Bonfim (S-DEC); 2024-10-05 loss vs Joaquin Buckley (KO/TKO); 2023-12-16 loss vs Shavkat Rakhmonov (SUB)
- recent fights, Charles Radtke: 2026-04-11 win vs Francisco Prado (U-DEC); 2025-11-01 win vs Daniel Frunza (SUB); 2025-05-10 loss vs Mike Malott (KO/TKO)
- independent model votes for Stephen Thompson: logistic 52.4%, calibrated GBM 33.5%. Their spread is a sensitivity check, not a confidence interval.

| Pre-fight evidence | Stephen Thompson | Charles Radtke |
|---|---:|---:|
| Age | 43.76 | 36.35 |
| Reach (cm) | 190.50 | 182.88 |
| UFC fights | 22.00 | 7.00 |
| Days since UFC fight | 490.00 | 217.00 |
| Last 3: sig. strikes landed/min | 2.88 | 1.86 |
| Last 3: sig. strikes absorbed/min | 2.74 | 2.03 |
| Last 5: takedowns/15 min | 0.00 | 2.59 |
| Last 5: takedown defense (fraction) | 0.54 | unavailable |
| Last 5: control-time fraction | 0.03 | 0.52 |
| Last 5: opponent pre-fight Elo | 1704.47 | 1501.18 |

- method: Stephen Thompson by KO 14% / sub 3% / dec 20%; Charles Radtke by KO 13% / sub 17% / dec 32%
- pick outcome: Charles Radtke by decision (32%)
- how it ends: finish 47% (R1 24% / R2 15% / R3 9%) vs. decision 53%
- likeliest endings: Charles Radtke by decision (32%), Stephen Thompson by decision (20%), Charles Radtke by submission, round 1 (9%)
- drivers (log-odds): diff_strike_elo +0.33, diff_age -0.15, diff_opp_elo_l5 +0.13, diff_td15_l5 -0.11, diff_grapple_elo -0.11

| ending | R1 | R2 | R3 | any round |
|---|---|---|---|---|
| Stephen Thompson by KO/TKO | 6.5% | 4.4% | 2.7% | **13.7%** |
| Stephen Thompson by submission | 1.5% | 1.1% | 0.7% | **3.4%** |
| Charles Radtke by KO/TKO | 7.0% | 4.1% | 2.1% | **13.2%** |
| Charles Radtke by submission | 8.6% | 5.5% | 2.9% | **17.0%** |
| decision (either fighter) | — | — | — | **52.7%** |

## Drew Dober vs. Chris Duncan — Lightweight
P(Drew Dober wins) = 0.249  ->  pick: Chris Duncan (75%)
- research: Form: Chris Duncan holds the pre-fight-expectation-adjusted form edge (cold vs hot over the last 5).
- research: Style record: Chris Duncan is 75% against strikers in the UFC.
- research: Common opponents: 3 shared names on the record.
- recent fights, Drew Dober: 2026-03-07 win vs Michael Johnson (KO/TKO); 2025-10-18 win vs Kyle Prepolec (KO/TKO); 2025-03-29 loss vs Manuel Torres (KO/TKO)
- recent fights, Chris Duncan: 2026-04-04 loss vs Renato Moicano (SUB); 2025-12-06 win vs Terrance McKinney (SUB); 2025-08-02 win vs Mateusz Rebecki (U-DEC)
- independent model votes for Drew Dober: logistic 26.4%, calibrated GBM 24.6%. Their spread is a sensitivity check, not a confidence interval.

| Pre-fight evidence | Drew Dober | Chris Duncan |
|---|---:|---:|
| Age | 38.07 | 33.51 |
| Reach (cm) | 177.80 | 180.34 |
| UFC fights | 27.00 | 8.00 |
| Days since UFC fight | 252.00 | 224.00 |
| Last 3: sig. strikes landed/min | 5.43 | 6.10 |
| Last 3: sig. strikes absorbed/min | 5.08 | 6.45 |
| Last 5: takedowns/15 min | 0.32 | 1.97 |
| Last 5: takedown defense (fraction) | 0.67 | 0.60 |
| Last 5: control-time fraction | 0.03 | 0.19 |
| Last 5: opponent pre-fight Elo | 1561.73 | 1581.97 |

- skill-only research model P(Drew Dober) = 0.249; vig-free market = 0.407 (gap -0.158). Market shown for comparison only.
- method: Drew Dober by KO 11% / sub 2% / dec 12%; Chris Duncan by KO 21% / sub 24% / dec 31%
- pick outcome: Chris Duncan by decision (31%)
- how it ends: finish 58% (R1 31% / R2 18% / R3 8%) vs. decision 42%
- likeliest endings: Chris Duncan by decision (31%), Chris Duncan by submission, round 1 (13%), Chris Duncan by KO/TKO, round 1 (12%)
- drivers (log-odds): diff_age -0.18, f2_age_past_prime -0.12, diff_opp_elo_l5 -0.11, diff_style_grapple_strike -0.10, diff_strike_elo +0.09

| ending | R1 | R2 | R3 | any round |
|---|---|---|---|---|
| Drew Dober by KO/TKO | 5.2% | 3.6% | 2.3% | **11.1%** |
| Drew Dober by submission | 1.0% | 0.7% | 0.5% | **2.2%** |
| Chris Duncan by KO/TKO | 12.0% | 6.2% | 2.5% | **20.6%** |
| Chris Duncan by submission | 13.1% | 7.4% | 3.1% | **23.7%** |
| decision (either fighter) | — | — | — | **42.4%** |

## Jim Miller vs. Terrance McKinney — Lightweight
P(Jim Miller wins) = 0.322  ->  pick: Terrance McKinney (68%)
- research: Wrestling contrast: Terrance McKinney lands 2.8 takedowns/15 into Jim Miller's 45% TDD.
- research: Last fights: Jim Miller won last time out; Terrance McKinney lost last time out.
- research: Common opponents: 2 shared names on the record.
- recent fights, Jim Miller: 2026-05-09 win vs Jared Gordon (SUB); 2025-04-12 loss vs Chase Hooper (U-DEC); 2024-11-16 win vs Damon Jackson (SUB)
- recent fights, Terrance McKinney: 2026-07-11 loss vs King Green (KO/TKO); 2026-03-28 win vs Kyle Nelson (KO/TKO); 2025-12-06 loss vs Chris Duncan (SUB)
- independent model votes for Jim Miller: logistic 27.0%, calibrated GBM 33.4%. Their spread is a sensitivity check, not a confidence interval.

| Pre-fight evidence | Jim Miller | Terrance McKinney |
|---|---:|---:|
| Age | 43.21 | 32.16 |
| Reach (cm) | 180.34 | 185.42 |
| UFC fights | 47.00 | 14.00 |
| Days since UFC fight | 189.00 | 126.00 |
| Last 3: sig. strikes landed/min | 1.51 | 11.29 |
| Last 3: sig. strikes absorbed/min | 2.07 | 10.40 |
| Last 5: takedowns/15 min | 0.91 | 2.77 |
| Last 5: takedown defense (fraction) | 0.45 | 0.50 |
| Last 5: control-time fraction | 0.11 | 0.39 |
| Last 5: opponent pre-fight Elo | 1583.93 | 1573.15 |

- skill-only research model P(Jim Miller) = 0.322; vig-free market = 0.354 (gap -0.032). Market shown for comparison only.
- method: Jim Miller by KO 12% / sub 13% / dec 7%; Terrance McKinney by KO 27% / sub 17% / dec 24%
- pick outcome: Terrance McKinney by KO/TKO, round 1 (method 27%; round given method 64%; exact outcome 17%)
- how it ends: finish 69% (R1 42% / R2 19% / R3 8%) vs. decision 31%
- likeliest endings: Terrance McKinney by decision (24%), Terrance McKinney by KO/TKO, round 1 (17%), Terrance McKinney by submission, round 1 (11%)
- drivers (log-odds): diff_age -0.34, diff_strike_elo -0.18, diff_grapple_elo -0.09, f2_age_past_prime -0.08, diff_style_grapple_strike +0.08

| ending | R1 | R2 | R3 | any round |
|---|---|---|---|---|
| Jim Miller by KO/TKO | 7.2% | 3.7% | 1.6% | **12.4%** |
| Jim Miller by submission | 7.2% | 4.1% | 1.8% | **13.0%** |
| Terrance McKinney by KO/TKO | 16.8% | 6.9% | 2.8% | **26.5%** |
| Terrance McKinney by submission | 10.6% | 4.7% | 2.0% | **17.3%** |
| decision (either fighter) | — | — | — | **30.7%** |

## Donte Johnson vs. Cesar Almeida — Middleweight
P(Donte Johnson wins) = 0.790  ->  pick: Donte Johnson (79%)
- research: Form: Donte Johnson holds the pre-fight-expectation-adjusted form edge (hot vs cold over the last 5).
- research: Style record: Donte Johnson is 100% against strikers in the UFC.
- recent fights, Donte Johnson: 2026-08-15 win vs Eric McConico (KO/TKO); 2026-03-07 win vs Cody Brundage (S-DEC); 2025-11-01 win vs Sedriques Dumas (SUB)
- recent fights, Cesar Almeida: 2026-07-11 loss vs Damian Pinas (KO/TKO); 2025-12-13 loss vs Cezary Oleksiejczuk (U-DEC); 2025-01-11 win vs Abdul Razak Alhassan (KO/TKO)
- independent model votes for Donte Johnson: logistic 81.1%, calibrated GBM 78.5%. Their spread is a sensitivity check, not a confidence interval.

| Pre-fight evidence | Donte Johnson | Cesar Almeida |
|---|---:|---:|
| Age | 27.80 | 38.63 |
| Reach (cm) | 187.96 | 187.96 |
| UFC fights | 3.00 | 6.00 |
| Days since UFC fight | 91.00 | 126.00 |
| Last 3: sig. strikes landed/min | 2.86 | 2.88 |
| Last 3: sig. strikes absorbed/min | 1.82 | 2.33 |
| Last 5: takedowns/15 min | 1.95 | 0.28 |
| Last 5: takedown defense (fraction) | 0.77 | 0.48 |
| Last 5: control-time fraction | 0.29 | 0.06 |
| Last 5: opponent pre-fight Elo | 1484.12 | 1511.87 |

- skill-only research model P(Donte Johnson) = 0.790; vig-free market = 0.608 (gap +0.181). Market shown for comparison only.
- method: Donte Johnson by KO 34% / sub 15% / dec 30%; Cesar Almeida by KO 8% / sub 2% / dec 11%
- pick outcome: Donte Johnson by KO/TKO, round 1 (method 34%; round given method 54%; exact outcome 18%)
- how it ends: finish 60% (R1 31% / R2 20% / R3 9%) vs. decision 40%
- likeliest endings: Donte Johnson by decision (30%), Donte Johnson by KO/TKO, round 1 (18%), Donte Johnson by KO/TKO, round 2 (11%)
- drivers (log-odds): diff_age +0.33, diff_strike_elo -0.12, diff_elo +0.11, diff_td15_l5 +0.10, diff_grapple_elo +0.09

| ending | R1 | R2 | R3 | any round |
|---|---|---|---|---|
| Donte Johnson by KO/TKO | 18.5% | 11.4% | 4.5% | **34.3%** |
| Donte Johnson by submission | 7.7% | 5.2% | 2.1% | **15.0%** |
| Cesar Almeida by KO/TKO | 3.6% | 2.8% | 1.8% | **8.1%** |
| Cesar Almeida by submission | 0.9% | 0.8% | 0.5% | **2.2%** |
| decision (either fighter) | — | — | — | **40.4%** |

## Jared Gordon vs. Melquizael Costa — Lightweight
P(Jared Gordon wins) = 0.237  ->  pick: Melquizael Costa (76%)
- research: Style: both profile as strikers — a same-look fight.
- research: Pace: Jared Gordon is the volume striker (6.5 vs 4.7 SLpM).
- research: Form: Melquizael Costa holds the pre-fight-expectation-adjusted form edge (mixed vs hot over the last 5).
- research: Style record: Jared Gordon is 47% against strikers in the UFC.
- research: Common opponents (1): Jared Gordon's record against them is better.
- recent fights, Jared Gordon: 2026-05-09 loss vs Jim Miller (SUB); 2025-09-13 loss vs Rafa Garcia (KO/TKO); 2025-05-17 win vs Thiago Moises (KO/TKO)
- recent fights, Melquizael Costa: 2026-05-16 loss vs Arnold Allen (U-DEC); 2026-02-21 win vs Dan Ige (KO/TKO); 2025-12-13 win vs Morgan Charriere (KO/TKO)
- independent model votes for Jared Gordon: logistic 20.0%, calibrated GBM 24.6%. Their spread is a sensitivity check, not a confidence interval.

| Pre-fight evidence | Jared Gordon | Melquizael Costa |
|---|---:|---:|
| Age | 38.19 | 30.17 |
| Reach (cm) | 172.72 | 180.34 |
| UFC fights | 18.00 | 10.00 |
| Days since UFC fight | 189.00 | 182.00 |
| Last 3: sig. strikes landed/min | 4.04 | 3.95 |
| Last 3: sig. strikes absorbed/min | 5.37 | 3.43 |
| Last 5: takedowns/15 min | 1.53 | 0.98 |
| Last 5: takedown defense (fraction) | 0.33 | 0.51 |
| Last 5: control-time fraction | 0.17 | 0.12 |
| Last 5: opponent pre-fight Elo | 1616.88 | 1625.00 |

- skill-only research model P(Jared Gordon) = 0.237; vig-free market = 0.244 (gap -0.008). Market shown for comparison only.
- method: Jared Gordon by KO 7% / sub 2% / dec 14%; Melquizael Costa by KO 30% / sub 23% / dec 23%
- pick outcome: Melquizael Costa by KO/TKO, round 1 (method 30%; round given method 52%; exact outcome 16%)
- how it ends: finish 63% (R1 32% / R2 21% / R3 10%) vs. decision 37%
- likeliest endings: Melquizael Costa by decision (23%), Melquizael Costa by KO/TKO, round 1 (16%), Jared Gordon by decision (14%)
- drivers (log-odds): diff_age -0.19, diff_elo -0.13, diff_grapple_elo +0.09, f1_age -0.09, f2_age_past_prime -0.07

| ending | R1 | R2 | R3 | any round |
|---|---|---|---|---|
| Jared Gordon by KO/TKO | 3.4% | 2.5% | 1.4% | **7.3%** |
| Jared Gordon by submission | 1.1% | 0.9% | 0.5% | **2.4%** |
| Melquizael Costa by KO/TKO | 15.5% | 9.9% | 4.5% | **29.9%** |
| Melquizael Costa by submission | 11.7% | 8.0% | 3.7% | **23.4%** |
| decision (either fighter) | — | — | — | **37.0%** |

## Macy Chiasson vs. Beatriz Mesquita — Women's Bantamweight
P(Macy Chiasson wins) = 0.741  ->  pick: Macy Chiasson (74%)
- CAUTION: no UFC history for Beatriz Mesquita (debut or misspelled name?) — prediction is weak.
- research: Last fights: Macy Chiasson lost last time out.
- recent fights, Macy Chiasson: 2026-02-28 loss vs Ailin Perez (U-DEC); 2025-10-04 loss vs Yana Santos (U-DEC); 2025-05-31 loss vs Ketlen Vieira (U-DEC)
- independent model votes for Macy Chiasson: logistic 68.8%, calibrated GBM 75.4%. Their spread is a sensitivity check, not a confidence interval.

| Pre-fight evidence | Macy Chiasson | Beatriz Mesquita |
|---|---:|---:|
| Age | 35.30 | unavailable |
| Reach (cm) | 182.88 | unavailable |
| UFC fights | 14.00 | 0.00 |
| Days since UFC fight | 259.00 | unavailable |
| Last 3: sig. strikes landed/min | 1.87 | unavailable |
| Last 3: sig. strikes absorbed/min | 2.67 | unavailable |
| Last 5: takedowns/15 min | 1.34 | unavailable |
| Last 5: takedown defense (fraction) | 0.61 | unavailable |
| Last 5: control-time fraction | 0.22 | unavailable |
| Last 5: opponent pre-fight Elo | 1593.57 | unavailable |

- skill-only research model P(Macy Chiasson) = 0.741; vig-free market = 0.311 (gap +0.431). Market shown for comparison only.
- method: Macy Chiasson by KO 21% / sub 18% / dec 35%; Beatriz Mesquita by KO 10% / sub 6% / dec 10%
- pick outcome: Macy Chiasson by decision (35%)
- how it ends: finish 56% (R1 34% / R2 15% / R3 7%) vs. decision 44%
- likeliest endings: Macy Chiasson by decision (35%), Macy Chiasson by KO/TKO, round 1 (13%), Macy Chiasson by submission, round 1 (11%)
- drivers (log-odds): f2_reach_cm +0.40, diff_height_cm -0.31, f1_reach_cm +0.25, diff_style_reach_striker +0.09, diff_strike_elo +0.08

| ending | R1 | R2 | R3 | any round |
|---|---|---|---|---|
| Macy Chiasson by KO/TKO | 12.8% | 5.7% | 2.6% | **21.1%** |
| Macy Chiasson by submission | 10.7% | 5.1% | 2.3% | **18.1%** |
| Beatriz Mesquita by KO/TKO | 6.6% | 2.7% | 1.1% | **10.3%** |
| Beatriz Mesquita by submission | 3.6% | 1.6% | 0.7% | **5.9%** |
| decision (either fighter) | — | — | — | **44.5%** |

## Evan Elder vs. Samuel Sanches — Lightweight
P(Evan Elder wins) = 0.542  ->  pick: Evan Elder (54%; close fight)
- CAUTION: no UFC history for Samuel Sanches (debut or misspelled name?) — prediction is weak.
- research: Last fights: Evan Elder won last time out.
- recent fights, Evan Elder: 2025-04-26 win vs Gauge Young (U-DEC); 2024-07-13 win vs Darrius Flowers (SUB); 2023-07-15 win vs Genaro Valdez (U-DEC)
- independent model votes for Evan Elder: logistic 54.6%, calibrated GBM 54.1%. Their spread is a sensitivity check, not a confidence interval.

| Pre-fight evidence | Evan Elder | Samuel Sanches |
|---|---:|---:|
| Age | 29.59 | 23.79 |
| Reach (cm) | 182.88 | 187.96 |
| UFC fights | 5.00 | 0.00 |
| Days since UFC fight | 567.00 | unavailable |
| Last 3: sig. strikes landed/min | 6.96 | unavailable |
| Last 3: sig. strikes absorbed/min | 4.60 | unavailable |
| Last 5: takedowns/15 min | 0.48 | unavailable |
| Last 5: takedown defense (fraction) | 0.40 | unavailable |
| Last 5: control-time fraction | 0.09 | unavailable |
| Last 5: opponent pre-fight Elo | 1465.83 | unavailable |

- skill-only research model P(Evan Elder) = 0.542; vig-free market = 0.478 (gap +0.064). Market shown for comparison only.
- method: Evan Elder by KO 14% / sub 8% / dec 32%; Samuel Sanches by KO 20% / sub 9% / dec 17%
- pick outcome: Evan Elder by decision (32%)
- how it ends: finish 51% (R1 28% / R2 15% / R3 8%) vs. decision 49%
- likeliest endings: Evan Elder by decision (32%), Samuel Sanches by decision (17%), Samuel Sanches by KO/TKO, round 1 (11%)
- drivers (log-odds): diff_age -0.15, diff_strike_elo +0.15, diff_elo +0.07, diff_style_grapple_strike +0.06, f1_layoff_days -0.05

| ending | R1 | R2 | R3 | any round |
|---|---|---|---|---|
| Evan Elder by KO/TKO | 7.5% | 4.5% | 2.4% | **14.4%** |
| Evan Elder by submission | 4.0% | 2.6% | 1.4% | **8.1%** |
| Samuel Sanches by KO/TKO | 11.4% | 5.7% | 2.7% | **19.8%** |
| Samuel Sanches by submission | 4.7% | 2.6% | 1.2% | **8.6%** |
| decision (either fighter) | — | — | — | **49.1%** |

## Juan Diaz vs. Alateng Heili — Bantamweight
P(Juan Diaz wins) = 0.761  ->  pick: Juan Diaz (76%)
- CAUTION: no UFC history for Alateng Heili (debut or misspelled name?) — prediction is weak.
- research: Last fights: Juan Diaz won last time out.
- recent fights, Juan Diaz: 2026-05-16 win vs Malcolm Wellmaker (SUB)
- independent model votes for Juan Diaz: logistic 66.4%, calibrated GBM 78.5%. Their spread is a sensitivity check, not a confidence interval.

| Pre-fight evidence | Juan Diaz | Alateng Heili |
|---|---:|---:|
| Age | 28.45 | unavailable |
| Reach (cm) | unavailable | unavailable |
| UFC fights | 1.00 | 0.00 |
| Days since UFC fight | 182.00 | unavailable |
| Last 3: sig. strikes landed/min | 1.42 | unavailable |
| Last 3: sig. strikes absorbed/min | 1.64 | unavailable |
| Last 5: takedowns/15 min | 8.21 | unavailable |
| Last 5: takedown defense (fraction) | unavailable | unavailable |
| Last 5: control-time fraction | 0.42 | unavailable |
| Last 5: opponent pre-fight Elo | 1521.54 | unavailable |

- skill-only research model P(Juan Diaz) = 0.761; vig-free market = 0.722 (gap +0.039). Market shown for comparison only.
- method: Juan Diaz by KO 15% / sub 38% / dec 23%; Alateng Heili by KO 8% / sub 7% / dec 9%
- pick outcome: Juan Diaz by submission, round 1 (method 38%; round given method 59%; exact outcome 22%)
- how it ends: finish 68% (R1 41% / R2 19% / R3 8%) vs. decision 32%
- likeliest endings: Juan Diaz by decision (23%), Juan Diaz by submission, round 1 (22%), Juan Diaz by submission, round 2 (11%)
- drivers (log-odds): f1_age +0.24, f2_reach_cm +0.19, f2_age_past_prime +0.12, f2_age +0.12, f1_reach_cm +0.10

| ending | R1 | R2 | R3 | any round |
|---|---|---|---|---|
| Juan Diaz by KO/TKO | 9.2% | 4.0% | 1.8% | **15.0%** |
| Juan Diaz by submission | 22.5% | 10.6% | 4.7% | **37.8%** |
| Alateng Heili by KO/TKO | 4.9% | 2.2% | 1.0% | **8.2%** |
| Alateng Heili by submission | 4.0% | 2.0% | 0.9% | **6.9%** |
| decision (either fighter) | — | — | — | **32.1%** |

---
*Simulation/educational project. No betting advice. The market knows more than this model.*