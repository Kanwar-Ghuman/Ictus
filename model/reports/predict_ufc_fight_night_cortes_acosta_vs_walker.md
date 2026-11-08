# UFC Fight Night: Cortes-Acosta vs. Walker — 2026-11-07

Point-in-time predictions from 8731 historical fights. Educational output — NOT betting advice; the backtest shows this model does not beat the market.

Name spellings resolved against ufcstats: Waldo Cortes-Acosta -> Waldo Cortes Acosta; Nina Milošević -> Nina Milosevic; Mantas Kondratavičius -> Mantas Kondratavicius; José Souza -> Jose Souza

Prediction mode: **market_aware**. Market layer enabled.
Historical results available through 2026-09-12.

## Waldo Cortes Acosta vs. Johnny Walker — Heavyweight
P(Waldo Cortes Acosta wins) = 0.588  ->  pick: Waldo Cortes Acosta (59%)
- verified context, Waldo Cortes Acosta: Waldo Cortes-Acosta (born October 3, 1991) is a Dominican professional mixed martial artist and professional boxer. He currently competes in the Heavyweight division of the Ultimate Fighting Championship (UFC). A professional since 2018, Cortes-Acosta  competed in the LFA, where he was the heavyweight champion and subsequently earned his UFC contract on Dana White's Contender Series, winning by first-round TKO. As of September 12, 2026, he is #8 in the Meta UFC heavyweight rankings.
- verified context, Johnny Walker: Johnnie Walker is a brand of whisky produced in Scotland.
Johnnie, Johnny, or Jonny Walker may also refer to:
- research: Style: both profile as strikers — a same-look fight.
- research: Last fights: Waldo Cortes Acosta lost last time out; Johnny Walker lost last time out.
- research: Style record: Waldo Cortes Acosta is 71% against strikers in the UFC.
- research: Common opponents: 1 shared names on the record.
- recent fights, Waldo Cortes Acosta: 2026-09-12 loss vs Curtis Blaydes (U-DEC); 2026-05-09 loss vs Alexander Volkov (U-DEC); 2026-01-24 win vs Derrick Lewis (KO/TKO)
- recent fights, Johnny Walker: 2026-04-11 loss vs Dominick Reyes (S-DEC); 2025-08-23 win vs Zhang Mingyang (KO/TKO); 2024-06-22 loss vs Volkan Oezdemir (KO/TKO)
- independent model votes for Waldo Cortes Acosta: logistic 58.9%, calibrated GBM 50.0%. Their spread is a sensitivity check, not a confidence interval.

| Pre-fight evidence | Waldo Cortes Acosta | Johnny Walker |
|---|---:|---:|
| Age | 35.10 | 34.61 |
| Reach (cm) | 198.12 | 208.28 |
| UFC fights | 14.00 | 16.00 |
| Days since UFC fight | 56.00 | 210.00 |
| Last 3: sig. strikes landed/min | 3.30 | 4.27 |
| Last 3: sig. strikes absorbed/min | 3.14 | 3.63 |
| Last 5: takedowns/15 min | 0.34 | 0.00 |
| Last 5: takedown defense (fraction) | 0.67 | 0.00 |
| Last 5: control-time fraction | 0.05 | 0.04 |
| Last 5: opponent pre-fight Elo | 1678.39 | 1699.35 |

- skill-only research model P(Waldo Cortes Acosta) = 0.518; vig-free market = 0.664 (gap -0.146). Shipped number mixes both; deeper UFC history weights skill more.
- method: Waldo Cortes Acosta by KO 40% / sub 3% / dec 15%; Johnny Walker by KO 25% / sub 3% / dec 13%
- pick outcome: Waldo Cortes Acosta by KO/TKO, round 1 (method 40%; round given method 38%; exact outcome 15%)
- how it ends: finish 71% (R1 27% / R2 21% / R3 12% / R4 6% / R5 5%) vs. decision 29%
- likeliest endings: Waldo Cortes Acosta by decision (15%), Waldo Cortes Acosta by KO/TKO, round 1 (15%), Johnny Walker by decision (13%)
- drivers (log-odds): diff_age -0.12, diff_opp_elo_l5 -0.10, diff_sig_acc_l5 -0.08, diff_dec_win_rate -0.07, diff_strike_elo +0.06

| ending | R1 | R2 | R3 | R4 | R5 | any round |
|---|---|---|---|---|---|---|
| Waldo Cortes Acosta by KO/TKO | 15.2% | 12.0% | 6.8% | 3.5% | 2.9% | **40.4%** |
| Waldo Cortes Acosta by submission | 1.0% | 0.9% | 0.6% | 0.3% | 0.2% | **3.0%** |
| Johnny Walker by KO/TKO | 9.8% | 7.5% | 4.0% | 2.0% | 1.5% | **24.7%** |
| Johnny Walker by submission | 1.1% | 0.9% | 0.6% | 0.3% | 0.2% | **3.1%** |
| decision (either fighter) | — | — | — | — | — | **28.8%** |

## Tatiana Suarez vs. Virna Jandiroba — Women's Strawweight
P(Tatiana Suarez wins) = 0.676  ->  pick: Tatiana Suarez (68%)
- verified context, Tatiana Suarez: Tatiana Yadira Suarez Padilla (born December 19, 1990) is an American professional mixed martial artist and former wrestler who currently competes in the women's Strawweight division of the Ultimate Fighting Championship (UFC). She was the strawweight tournament winner in the 23rd season of The Ultimate Fighter reality show. As of June 20, 2026, she is #3 in the Meta UFC women's strawweight rankings, and as of October 17, 2026, she is #8 in the UFC women's pound-for-pound rankings.
In wrestling, Suarez was a multi-time medalist in women's freestyle at the World Championships and World Junior Championships, a silver medalist at the World Cup, and a gold medalist at the Pan American Championships.
- verified context, Virna Jandiroba: Virna Carole Andrade Jandiroba (born May 30, 1988) is a Brazilian mixed martial artist who currently competes in the women's Strawweight division of the Ultimate Fighting Championship (UFC). She is a former Invicta Fighting Championships (Invicta) Strawweight champion. As of June 20, 2026, she is #2 in the Meta UFC women's strawweight rankings and as of March 24, 2026, she is #11 in the UFC women's pound-for-pound rankings.
- research: Wrestling contrast: Tatiana Suarez lands 2.9 takedowns/15 into Virna Jandiroba's 70% TDD.
- research: Last fights: Tatiana Suarez won last time out; Virna Jandiroba won last time out.
- research: Common opponents (3): Tatiana Suarez's record against them is better.
- recent fights, Tatiana Suarez: 2026-04-11 win vs Loopy Godinez (SUB); 2025-09-13 win vs Amanda Lemos (U-DEC); 2025-02-08 loss vs Zhang Weili (U-DEC)
- recent fights, Virna Jandiroba: 2026-04-04 win vs Tabatha Ricci (U-DEC); 2025-10-25 loss vs Mackenzie Dern (U-DEC); 2025-04-12 win vs Yan Xiaonan (U-DEC)
- independent model votes for Tatiana Suarez: logistic 69.0%, calibrated GBM 66.5%. Their spread is a sensitivity check, not a confidence interval.

| Pre-fight evidence | Tatiana Suarez | Virna Jandiroba |
|---|---:|---:|
| Age | 35.89 | 38.44 |
| Reach (cm) | 167.64 | 162.56 |
| UFC fights | 10.00 | 13.00 |
| Days since UFC fight | 210.00 | 217.00 |
| Last 3: sig. strikes landed/min | 0.93 | 2.60 |
| Last 3: sig. strikes absorbed/min | 1.98 | 3.13 |
| Last 5: takedowns/15 min | 2.91 | 3.95 |
| Last 5: takedown defense (fraction) | 0.40 | 0.70 |
| Last 5: control-time fraction | 0.47 | 0.50 |
| Last 5: opponent pre-fight Elo | 1665.64 | 1670.76 |

- skill-only research model P(Tatiana Suarez) = 0.670; vig-free market = 0.637 (gap +0.033). Shipped number mixes both; deeper UFC history weights skill more.
- method: Tatiana Suarez by KO 9% / sub 11% / dec 48%; Virna Jandiroba by KO 5% / sub 7% / dec 20%
- pick outcome: Tatiana Suarez by decision (48%)
- how it ends: finish 32% (R1 16% / R2 11% / R3 6%) vs. decision 68%
- likeliest endings: Tatiana Suarez by decision (48%), Virna Jandiroba by decision (20%), Tatiana Suarez by submission, round 1 (5%)
- drivers (log-odds): diff_strike_elo +0.22, diff_age +0.17, diff_pre_ufc_major_org_share +0.13, diff_elo +0.09, diff_career_win_pct +0.06

| ending | R1 | R2 | R3 | any round |
|---|---|---|---|---|
| Tatiana Suarez by KO/TKO | 4.4% | 2.8% | 1.5% | **8.7%** |
| Tatiana Suarez by submission | 5.2% | 3.6% | 1.9% | **10.7%** |
| Virna Jandiroba by KO/TKO | 2.5% | 1.7% | 0.9% | **5.2%** |
| Virna Jandiroba by submission | 3.4% | 2.5% | 1.3% | **7.2%** |
| decision (either fighter) | — | — | — | **68.3%** |

## Davey Grant vs. Elijah Smith — Bantamweight
P(Davey Grant wins) = 0.216  ->  pick: Elijah Smith (78%)
- verified context, Davey Grant: Davey Grant (born 18 December 1985) is an English mixed martial artist. He was one of the cast members for UFC TV series The Ultimate Fighter: Team Rousey vs. Team Tate and currently competes in the Bantamweight division of the Ultimate Fighting Championship (UFC).
- verified context, Elijah Smith: Elijah Smith may refer to:

Elijah F. Smith (1792–1879), mayor of Rochester, New York
Elijah Smith (footballer) (1860–?), English footballer
- research: Pace: Davey Grant is the volume striker (7.2 vs 3.7 SLpM).
- research: Form: Elijah Smith holds the pre-fight-expectation-adjusted form edge (mixed vs hot over the last 5).
- research: Style record: Elijah Smith is 100% against strikers in the UFC.
- recent fights, Davey Grant: 2026-04-25 win vs Adrian Luna Martinetti (U-DEC); 2025-10-18 loss vs Charles Jourdain (SUB); 2025-07-26 win vs Da'Mon Blackshear (U-DEC)
- recent fights, Elijah Smith: 2026-03-14 win vs SuYoung You (SUB); 2025-08-09 win vs Toshiomi Kazama (KO/TKO); 2025-02-15 win vs Vince Morales (U-DEC)
- independent model votes for Davey Grant: logistic 28.9%, calibrated GBM 24.6%. Their spread is a sensitivity check, not a confidence interval.

| Pre-fight evidence | Davey Grant | Elijah Smith |
|---|---:|---:|
| Age | 40.89 | 24.17 |
| Reach (cm) | 175.26 | 180.34 |
| UFC fights | 16.00 | 3.00 |
| Days since UFC fight | 196.00 | 238.00 |
| Last 3: sig. strikes landed/min | 7.16 | 3.69 |
| Last 3: sig. strikes absorbed/min | 4.75 | 1.70 |
| Last 5: takedowns/15 min | 0.00 | 1.78 |
| Last 5: takedown defense (fraction) | 0.73 | 0.46 |
| Last 5: control-time fraction | 0.01 | 0.33 |
| Last 5: opponent pre-fight Elo | 1548.14 | 1501.12 |

- skill-only research model P(Davey Grant) = 0.254; vig-free market = 0.263 (gap -0.008). Shipped number mixes both; deeper UFC history weights skill more.
- method: Davey Grant by KO 4% / sub 3% / dec 14%; Elijah Smith by KO 18% / sub 28% / dec 32%
- pick outcome: Elijah Smith by decision (32%)
- how it ends: finish 53% (R1 29% / R2 16% / R3 8%) vs. decision 47%
- likeliest endings: Elijah Smith by decision (32%), Elijah Smith by submission, round 1 (15%), Davey Grant by decision (14%)
- drivers (log-odds): diff_strike_elo +0.40, diff_age -0.38, f2_age_past_prime -0.11, diff_pre_ufc_major_org_share -0.09, diff_age_past_prime -0.08

| ending | R1 | R2 | R3 | any round |
|---|---|---|---|---|
| Davey Grant by KO/TKO | 1.8% | 1.4% | 0.9% | **4.1%** |
| Davey Grant by submission | 1.3% | 1.1% | 0.8% | **3.2%** |
| Elijah Smith by KO/TKO | 10.5% | 5.3% | 2.5% | **18.3%** |
| Elijah Smith by submission | 15.2% | 8.3% | 4.0% | **27.6%** |
| decision (either fighter) | — | — | — | **46.8%** |

## Billy Elekana vs. Lucas Fernando — Light Heavyweight
P(Billy Elekana wins) = 0.242  ->  pick: Lucas Fernando (76%)
- verified context, Billy Elekana: Billy Joseph Elekana (born May 28, 1995) is an American professional mixed martial artist. He currently competes in the Light Heavyweight division for the Ultimate Fighting Championship (UFC). He has previously competed on Professional Fighters League (PFL) and Legacy Fighting Alliance (LFA).
- research: Style: both profile as strikers — a same-look fight.
- research: Pace: Lucas Fernando is the volume striker (6.2 vs 2.7 SLpM).
- research: Form: Lucas Fernando holds the pre-fight-expectation-adjusted form edge (hot vs hot over the last 5).
- research: Style record: Billy Elekana is 67% against strikers in the UFC.
- recent fights, Billy Elekana: 2026-01-31 win vs Junior Tafa (SUB); 2025-11-01 win vs Kevin Christian (SUB); 2025-07-26 win vs Ibo Aslan (U-DEC)
- recent fights, Lucas Fernando: 2026-08-15 win vs Rafael Tobias (KO/TKO); 2026-05-29 win vs Leon Soares (KO/TKO); 2025-08-15 win vs Phillip Latu (KO/TKO)
- independent model votes for Billy Elekana: logistic 33.7%, calibrated GBM 39.8%. Their spread is a sensitivity check, not a confidence interval.

| Pre-fight evidence | Billy Elekana | Lucas Fernando |
|---|---:|---:|
| Age | 31.45 | 29.82 |
| Reach (cm) | 195.58 | 203.20 |
| UFC fights | 4.00 | 1.00 |
| Days since UFC fight | 280.00 | 84.00 |
| Last 3: sig. strikes landed/min | 2.83 | 6.18 |
| Last 3: sig. strikes absorbed/min | 2.98 | 1.16 |
| Last 5: takedowns/15 min | 0.85 | 0.00 |
| Last 5: takedown defense (fraction) | unavailable | 0.00 |
| Last 5: control-time fraction | 0.16 | 0.01 |
| Last 5: opponent pre-fight Elo | 1503.39 | 1450.71 |

- skill-only research model P(Billy Elekana) = 0.386; vig-free market = 0.257 (gap +0.129). Shipped number mixes both; deeper UFC history weights skill more.
- method: Billy Elekana by KO 6% / sub 10% / dec 8%; Lucas Fernando by KO 39% / sub 6% / dec 31%
- pick outcome: Lucas Fernando by KO/TKO, round 1 (method 39%; round given method 55%; exact outcome 21%)
- how it ends: finish 61% (R1 33% / R2 19% / R3 9%) vs. decision 39%
- likeliest endings: Lucas Fernando by decision (31%), Lucas Fernando by KO/TKO, round 1 (21%), Lucas Fernando by KO/TKO, round 2 (12%)
- drivers (log-odds): diff_strike_elo -0.31, diff_age -0.12, diff_opp_elo_l5 +0.11, diff_elo +0.08, diff_sapm_l5 -0.06

| ending | R1 | R2 | R3 | any round |
|---|---|---|---|---|
| Billy Elekana by KO/TKO | 3.2% | 1.7% | 0.7% | **5.7%** |
| Billy Elekana by submission | 5.5% | 3.1% | 1.5% | **10.0%** |
| Lucas Fernando by KO/TKO | 21.3% | 11.8% | 5.9% | **39.0%** |
| Lucas Fernando by submission | 3.2% | 2.0% | 1.0% | **6.3%** |
| decision (either fighter) | — | — | — | **39.1%** |

## Priscila Cachoeira vs. Nina Milosevic — Women's Bantamweight
P(Priscila Cachoeira wins) = 0.149  ->  pick: Nina Milosevic (85%)
- research: Style: both profile as strikers — a same-look fight.
- research: Form: Nina Milosevic holds the pre-fight-expectation-adjusted form edge (cold vs hot over the last 5).
- research: Style record: Priscila Cachoeira is 42% against strikers in the UFC.
- recent fights, Priscila Cachoeira: 2026-06-06 loss vs Chelsea Chandler (SUB); 2026-02-07 loss vs Klaudia Sygula (U-DEC); 2025-08-09 loss vs Joselyne Edwards (KO/TKO)
- recent fights, Nina Milosevic: 2026-08-01 win vs Hailey Cowan (KO/TKO); 2026-02-14 win vs Dina Osman (DEC); 2025-07-05 win vs Desi Rahayu (KO/TKO)
- independent model votes for Priscila Cachoeira: logistic 4.9%, calibrated GBM 24.6%. Their spread is a sensitivity check, not a confidence interval.

| Pre-fight evidence | Priscila Cachoeira | Nina Milosevic |
|---|---:|---:|
| Age | 38.22 | 30.25 |
| Reach (cm) | 165.10 | unavailable |
| UFC fights | 14.00 | 1.00 |
| Days since UFC fight | 154.00 | 98.00 |
| Last 3: sig. strikes landed/min | 5.88 | 5.70 |
| Last 3: sig. strikes absorbed/min | 8.91 | 3.53 |
| Last 5: takedowns/15 min | 0.78 | 0.00 |
| Last 5: takedown defense (fraction) | 0.82 | 1.00 |
| Last 5: control-time fraction | 0.02 | 0.00 |
| Last 5: opponent pre-fight Elo | 1516.04 | 1393.07 |

- skill-only research model P(Priscila Cachoeira) = 0.206; vig-free market = 0.200 (gap +0.006). Shipped number mixes both; deeper UFC history weights skill more.
- method: Priscila Cachoeira by KO 5% / sub 1% / dec 8%; Nina Milosevic by KO 42% / sub 14% / dec 30%
- pick outcome: Nina Milosevic by KO/TKO, round 1 (method 42%; round given method 61%; exact outcome 25%)
- how it ends: finish 62% (R1 37% / R2 18% / R3 8%) vs. decision 38%
- likeliest endings: Nina Milosevic by decision (30%), Nina Milosevic by KO/TKO, round 1 (25%), Nina Milosevic by KO/TKO, round 2 (12%)
- drivers (log-odds): f2_reach_cm +0.31, diff_strike_elo -0.29, diff_age -0.23, diff_height_cm -0.20, f1_reach_cm +0.18

| ending | R1 | R2 | R3 | any round |
|---|---|---|---|---|
| Priscila Cachoeira by KO/TKO | 2.8% | 1.7% | 0.8% | **5.3%** |
| Priscila Cachoeira by submission | 0.7% | 0.5% | 0.2% | **1.4%** |
| Nina Milosevic by KO/TKO | 25.4% | 11.5% | 4.9% | **41.9%** |
| Nina Milosevic by submission | 7.9% | 3.9% | 1.8% | **13.6%** |
| decision (either fighter) | — | — | — | **37.8%** |

## Mitch Raposo vs. Marcos Degli — Flyweight
P(Mitch Raposo wins) = 0.390  ->  pick: Marcos Degli (61%)
- CAUTION: no UFC history for Marcos Degli (debut or misspelled name?) — prediction is weak. Pro record outside the UFC: 15-3-0.
- research: Last fights: Mitch Raposo won last time out.
- recent fights, Mitch Raposo: 2026-06-20 win vs Allan Nascimento (S-DEC); 2025-10-25 win vs Azat Maksum (U-DEC); 2025-04-12 loss vs Sumudaerji (S-DEC)
- recent fights, Marcos Degli: 2026-09-22 win vs Paris Moran (SUB); 2026-01-23 win vs Luis Aguiar (KO/TKO); 2025-07-11 win vs Matheus Severino (KO/TKO)
- independent model votes for Mitch Raposo: logistic 37.2%, calibrated GBM 59.4%. Their spread is a sensitivity check, not a confidence interval.

| Pre-fight evidence | Mitch Raposo | Marcos Degli |
|---|---:|---:|
| Age | 28.06 | 26.49 |
| Reach (cm) | 162.56 | unavailable |
| UFC fights | 4.00 | 0.00 |
| Days since UFC fight | 140.00 | unavailable |
| Last 3: sig. strikes landed/min | 1.71 | unavailable |
| Last 3: sig. strikes absorbed/min | 2.71 | unavailable |
| Last 5: takedowns/15 min | 1.75 | unavailable |
| Last 5: takedown defense (fraction) | 0.71 | unavailable |
| Last 5: control-time fraction | 0.10 | unavailable |
| Last 5: opponent pre-fight Elo | 1519.04 | unavailable |

- skill-only research model P(Mitch Raposo) = 0.550; vig-free market = 0.326 (gap +0.223). Shipped number mixes both; deeper UFC history weights skill more.
- method: Mitch Raposo by KO 10% / sub 9% / dec 20%; Marcos Degli by KO 18% / sub 13% / dec 31%
- pick outcome: Marcos Degli by decision (31%)
- how it ends: finish 49% (R1 26% / R2 15% / R3 8%) vs. decision 51%
- likeliest endings: Marcos Degli by decision (31%), Mitch Raposo by decision (20%), Marcos Degli by KO/TKO, round 1 (10%)
- drivers (log-odds): f2_reach_cm +0.39, diff_height_cm -0.26, f1_reach_cm +0.24, diff_strike_elo -0.11, f1_pre_ufc_layoff_days +0.11

| ending | R1 | R2 | R3 | any round |
|---|---|---|---|---|
| Mitch Raposo by KO/TKO | 4.9% | 3.2% | 2.0% | **10.1%** |
| Mitch Raposo by submission | 4.0% | 2.8% | 1.8% | **8.7%** |
| Marcos Degli by KO/TKO | 9.9% | 5.4% | 2.4% | **17.7%** |
| Marcos Degli by submission | 6.8% | 4.0% | 1.9% | **12.8%** |
| decision (either fighter) | — | — | — | **50.7%** |

## Keiichiro Nakamura vs. Ollie Schmid — Featherweight
P(Keiichiro Nakamura wins) = 0.786  ->  pick: Keiichiro Nakamura (79%)
- research: Style: both profile as strikers — a same-look fight.
- research: Form: Keiichiro Nakamura holds the pre-fight-expectation-adjusted form edge (hot vs cold over the last 5).
- recent fights, Keiichiro Nakamura: 2026-01-31 win vs Sebastian Szalay (KO/TKO); 2024-10-05 win vs Yusuke Kagiyama (KO/TKO); 2023-12-17 win vs Shun Murata (KO/TKO)
- recent fights, Ollie Schmid: 2026-05-02 loss vs Marwan Rahiki (KO/TKO); 2026-03-07 win vs Jeff Mesa (KO/TKO); 2025-07-05 win vs Ford Gerbes (KO/TKO)
- independent model votes for Keiichiro Nakamura: logistic 78.7%, calibrated GBM 66.3%. Their spread is a sensitivity check, not a confidence interval.

| Pre-fight evidence | Keiichiro Nakamura | Ollie Schmid |
|---|---:|---:|
| Age | 27.93 | 25.86 |
| Reach (cm) | 177.80 | unavailable |
| UFC fights | 1.00 | 1.00 |
| Days since UFC fight | 280.00 | 189.00 |
| Last 3: sig. strikes landed/min | 3.26 | 3.23 |
| Last 3: sig. strikes absorbed/min | 5.72 | 7.90 |
| Last 5: takedowns/15 min | 0.00 | 0.00 |
| Last 5: takedown defense (fraction) | 0.00 | unavailable |
| Last 5: control-time fraction | 0.00 | 0.00 |
| Last 5: opponent pre-fight Elo | 1500.00 | 1535.94 |

- skill-only research model P(Keiichiro Nakamura) = 0.688; vig-free market = 0.753 (gap -0.065). Shipped number mixes both; deeper UFC history weights skill more.
- method: Keiichiro Nakamura by KO 41% / sub 6% / dec 32%; Ollie Schmid by KO 10% / sub 3% / dec 8%
- pick outcome: Keiichiro Nakamura by KO/TKO, round 1 (method 41%; round given method 56%; exact outcome 23%)
- how it ends: finish 60% (R1 33% / R2 18% / R3 9%) vs. decision 40%
- likeliest endings: Keiichiro Nakamura by decision (32%), Keiichiro Nakamura by KO/TKO, round 1 (23%), Keiichiro Nakamura by KO/TKO, round 2 (12%)
- drivers (log-odds): f2_reach_cm +0.37, diff_height_cm -0.29, f1_reach_cm +0.27, diff_age -0.16, diff_style_reach_striker +0.07

| ending | R1 | R2 | R3 | any round |
|---|---|---|---|---|
| Keiichiro Nakamura by KO/TKO | 22.7% | 12.1% | 5.8% | **40.6%** |
| Keiichiro Nakamura by submission | 3.4% | 2.0% | 1.0% | **6.3%** |
| Ollie Schmid by KO/TKO | 5.3% | 3.2% | 1.5% | **10.0%** |
| Ollie Schmid by submission | 1.6% | 1.0% | 0.5% | **3.1%** |
| decision (either fighter) | — | — | — | **39.9%** |

## Gabriel Lorenço vs. Thomas Petersen — Heavyweight
P(Gabriel Lorenço wins) = 0.330  ->  pick: Thomas Petersen (67%)
- CAUTION: no UFC history for Gabriel Lorenço (debut or misspelled name?) — prediction is weak.
- context: f2 flagged late replacement — confidence dampened
- research: Last fights: Thomas Petersen lost last time out.
- recent fights, Thomas Petersen: 2026-07-25 loss vs Valter Walker (SUB); 2026-04-04 win vs Guilherme Pat (M-DEC); 2025-10-11 loss vs Vitor Petrino (KO/TKO)
- independent model votes for Gabriel Lorenço: logistic 32.8%, calibrated GBM 21.5%. Their spread is a sensitivity check, not a confidence interval.

| Pre-fight evidence | Gabriel Lorenço | Thomas Petersen |
|---|---:|---:|
| Age | unavailable | 31.61 |
| Reach (cm) | unavailable | 187.96 |
| UFC fights | 0.00 | 7.00 |
| Days since UFC fight | unavailable | 105.00 |
| Last 3: sig. strikes landed/min | unavailable | 1.63 |
| Last 3: sig. strikes absorbed/min | unavailable | 1.82 |
| Last 5: takedowns/15 min | unavailable | 3.32 |
| Last 5: takedown defense (fraction) | unavailable | 0.83 |
| Last 5: control-time fraction | unavailable | 0.56 |
| Last 5: opponent pre-fight Elo | unavailable | 1548.11 |

- method: Gabriel Lorenço by KO 18% / sub 6% / dec 9%; Thomas Petersen by KO 33% / sub 12% / dec 22%
- pick outcome: Thomas Petersen by KO/TKO, round 1 (method 33%; round given method 65%; exact outcome 21%)
- how it ends: finish 68% (R1 45% / R2 17% / R3 7%) vs. decision 32%
- likeliest endings: Thomas Petersen by decision (22%), Thomas Petersen by KO/TKO, round 1 (21%), Gabriel Lorenço by KO/TKO, round 1 (12%)
- drivers (log-odds): f2_reach_cm -0.43, diff_height_cm +0.31, f1_reach_cm -0.23, diff_strike_elo -0.11, diff_style_reach_striker -0.10

| ending | R1 | R2 | R3 | any round |
|---|---|---|---|---|
| Gabriel Lorenço by KO/TKO | 12.1% | 4.1% | 1.6% | **17.8%** |
| Gabriel Lorenço by submission | 4.0% | 1.5% | 0.6% | **6.1%** |
| Thomas Petersen by KO/TKO | 21.3% | 8.1% | 3.2% | **32.6%** |
| Thomas Petersen by submission | 7.7% | 3.1% | 1.3% | **12.0%** |
| decision (either fighter) | — | — | — | **31.5%** |

## Karine Silva vs. Gabriella Fernandes — Women's Flyweight
P(Karine Silva wins) = 0.733  ->  pick: Karine Silva (73%)
- research: Style: Karine Silva profiles as a wrestler; Gabriella Fernandes as a striker.
- research: Pace: Gabriella Fernandes is the volume striker (4.0 vs 2.0 SLpM).
- research: Form: Gabriella Fernandes holds the pre-fight-expectation-adjusted form edge (mixed vs hot over the last 5).
- research: Style record: Karine Silva is 57% against strikers in the UFC.
- research: Common opponents: 1 shared names on the record.
- recent fights, Karine Silva: 2026-04-18 loss vs Jasmine Jasudavicius (U-DEC); 2025-12-06 loss vs Maycee Barber (U-DEC); 2025-08-16 win vs Dione Barbosa (U-DEC)
- recent fights, Gabriella Fernandes: 2026-03-28 loss vs Casey O'Neill (KO/TKO); 2025-08-09 win vs Julija Stoliarenko (U-DEC); 2024-11-23 win vs Wang Cong (SUB)
- independent model votes for Karine Silva: logistic 68.5%, calibrated GBM 75.4%. Their spread is a sensitivity check, not a confidence interval.

| Pre-fight evidence | Karine Silva | Gabriella Fernandes |
|---|---:|---:|
| Age | 32.93 | 33.23 |
| Reach (cm) | 170.18 | 167.64 |
| UFC fights | 8.00 | 6.00 |
| Days since UFC fight | 203.00 | 224.00 |
| Last 3: sig. strikes landed/min | 1.38 | 3.15 |
| Last 3: sig. strikes absorbed/min | 2.31 | 4.89 |
| Last 5: takedowns/15 min | 1.80 | 0.53 |
| Last 5: takedown defense (fraction) | 0.29 | 0.76 |
| Last 5: control-time fraction | 0.23 | 0.06 |
| Last 5: opponent pre-fight Elo | 1619.08 | 1499.98 |

- skill-only research model P(Karine Silva) = 0.740; vig-free market = 0.663 (gap +0.078). Shipped number mixes both; deeper UFC history weights skill more.
- method: Karine Silva by KO 11% / sub 16% / dec 46%; Gabriella Fernandes by KO 7% / sub 3% / dec 17%
- pick outcome: Karine Silva by decision (46%)
- how it ends: finish 37% (R1 19% / R2 12% / R3 6%) vs. decision 63%
- likeliest endings: Karine Silva by decision (46%), Gabriella Fernandes by decision (17%), Karine Silva by submission, round 1 (8%)
- drivers (log-odds): diff_strike_elo +0.41, diff_opp_elo_l5 +0.18, diff_elo +0.11, diff_age +0.08, diff_sapm_l5 +0.05

| ending | R1 | R2 | R3 | any round |
|---|---|---|---|---|
| Karine Silva by KO/TKO | 6.1% | 3.6% | 1.6% | **11.4%** |
| Karine Silva by submission | 8.3% | 5.4% | 2.5% | **16.1%** |
| Gabriella Fernandes by KO/TKO | 3.6% | 2.4% | 1.2% | **7.2%** |
| Gabriella Fernandes by submission | 1.4% | 1.0% | 0.5% | **2.8%** |
| decision (either fighter) | — | — | — | **62.5%** |

## Jose Delano vs. Murtazali Magomedov — Featherweight
P(Jose Delano wins) = 0.480  ->  pick: Murtazali Magomedov (52%; close fight)
- research: Wrestling contrast: Murtazali Magomedov lands 11.7 takedowns/15 into Jose Delano's 100% TDD.
- research: Last fights: Jose Delano won last time out; Murtazali Magomedov won last time out.
- recent fights, Jose Delano: 2026-04-04 win vs Robert Ruchala (U-DEC); 2025-08-19 win vs Manuel Exposito (DEC); 2025-02-07 win vs Abu-Muslim Alikhanov (KO/TKO)
- recent fights, Murtazali Magomedov: 2026-06-20 win vs Melsik Baghdasaryan (SUB)
- independent model votes for Jose Delano: logistic 40.1%, calibrated GBM 37.8%. Their spread is a sensitivity check, not a confidence interval.

| Pre-fight evidence | Jose Delano | Murtazali Magomedov |
|---|---:|---:|
| Age | 30.15 | 27.20 |
| Reach (cm) | 177.80 | 177.80 |
| UFC fights | 1.00 | 1.00 |
| Days since UFC fight | 217.00 | 140.00 |
| Last 3: sig. strikes landed/min | 7.13 | 3.90 |
| Last 3: sig. strikes absorbed/min | 4.47 | 2.34 |
| Last 5: takedowns/15 min | 0.00 | 11.69 |
| Last 5: takedown defense (fraction) | 1.00 | unavailable |
| Last 5: control-time fraction | 0.04 | 0.35 |
| Last 5: opponent pre-fight Elo | 1472.06 | 1530.55 |

- skill-only research model P(Jose Delano) = 0.383; vig-free market = 0.522 (gap -0.139). Shipped number mixes both; deeper UFC history weights skill more.
- method: Jose Delano by KO 15% / sub 8% / dec 26%; Murtazali Magomedov by KO 12% / sub 13% / dec 27%
- pick outcome: Murtazali Magomedov by decision (27%)
- how it ends: finish 47% (R1 27% / R2 15% / R3 6%) vs. decision 53%
- likeliest endings: Murtazali Magomedov by decision (27%), Jose Delano by decision (26%), Jose Delano by KO/TKO, round 1 (8%)
- drivers (log-odds): diff_age -0.18, diff_opp_elo_l5 -0.13, diff_strike_elo +0.10, diff_td15_l5 -0.10, diff_sapm_l5 -0.06

| ending | R1 | R2 | R3 | any round |
|---|---|---|---|---|
| Jose Delano by KO/TKO | 7.8% | 4.7% | 2.1% | **14.7%** |
| Jose Delano by submission | 3.9% | 2.5% | 1.2% | **7.6%** |
| Murtazali Magomedov by KO/TKO | 7.1% | 3.4% | 1.4% | **11.9%** |
| Murtazali Magomedov by submission | 7.6% | 3.9% | 1.7% | **13.3%** |
| decision (either fighter) | — | — | — | **52.5%** |

## Austin Bashi vs. Carlos Calderon — Featherweight
P(Austin Bashi wins) = 0.726  ->  pick: Austin Bashi (73%)
- CAUTION: no UFC history for Carlos Calderon (debut or misspelled name?) — prediction is weak. Pro record outside the UFC: 1-0-0.
- context: f2 flagged short notice — confidence dampened
- research: Last fights: Austin Bashi lost last time out.
- recent fights, Austin Bashi: 2026-07-18 loss vs Jose Delgado (U-DEC); 2025-08-02 win vs John Yannis (SUB); 2025-01-11 loss vs Christian Rodriguez (U-DEC)
- recent fights, Carlos Calderon: 2011-06-04 win vs Alex Doncel (KO/TKO)
- independent model votes for Austin Bashi: logistic 50.0%, calibrated GBM 68.4%. Their spread is a sensitivity check, not a confidence interval.

| Pre-fight evidence | Austin Bashi | Carlos Calderon |
|---|---:|---:|
| Age | 25.11 | 30.74 |
| Reach (cm) | 177.80 | 180.34 |
| UFC fights | 3.00 | 0.00 |
| Days since UFC fight | 112.00 | unavailable |
| Last 3: sig. strikes landed/min | 1.69 | unavailable |
| Last 3: sig. strikes absorbed/min | 2.35 | unavailable |
| Last 5: takedowns/15 min | 3.12 | unavailable |
| Last 5: takedown defense (fraction) | 0.57 | unavailable |
| Last 5: control-time fraction | 0.35 | unavailable |
| Last 5: opponent pre-fight Elo | 1560.51 | unavailable |

- skill-only research model P(Austin Bashi) = 0.647; vig-free market = 0.830 (gap -0.182). Shipped number mixes both; deeper UFC history weights skill more.
- method: Austin Bashi by KO 12% / sub 30% / dec 30%; Carlos Calderon by KO 12% / sub 2% / dec 13%
- pick outcome: Austin Bashi by decision (30%)
- how it ends: finish 57% (R1 31% / R2 17% / R3 8%) vs. decision 43%
- likeliest endings: Austin Bashi by decision (30%), Austin Bashi by submission, round 1 (17%), Carlos Calderon by decision (13%)
- drivers (log-odds): diff_age +0.13, diff_style_grapple_strike +0.07, diff_career_win_pct +0.06, diff_pre_ufc_major_org_share +0.04, diff_pre_ufc_win_pct +0.03

| ending | R1 | R2 | R3 | any round |
|---|---|---|---|---|
| Austin Bashi by KO/TKO | 7.1% | 3.7% | 1.6% | **12.4%** |
| Austin Bashi by submission | 16.6% | 9.4% | 4.1% | **30.0%** |
| Carlos Calderon by KO/TKO | 6.5% | 3.7% | 1.9% | **12.1%** |
| Carlos Calderon by submission | 1.1% | 0.7% | 0.4% | **2.2%** |
| decision (either fighter) | — | — | — | **43.2%** |

## Mantas Kondratavicius vs. Andre Petroski — Middleweight
P(Mantas Kondratavicius wins) = 0.687  ->  pick: Mantas Kondratavicius (69%)
- context: f2 flagged late replacement — confidence dampened
- research: Wrestling contrast: Mantas Kondratavicius lands 2.0 takedowns/15 into Andre Petroski's 92% TDD.
- research: Form: Mantas Kondratavicius holds the pre-fight-expectation-adjusted form edge (hot vs cold over the last 5).
- recent fights, Mantas Kondratavicius: 2026-03-21 win vs Antonio Trocoli (U-DEC); 2025-09-23 win vs Djani Barbir (KO/TKO); 2025-03-14 win vs Michael Tchamou (KO/TKO)
- recent fights, Andre Petroski: 2026-05-16 loss vs Cody Brundage (KO/TKO); 2025-09-27 loss vs Cam Rowston (KO/TKO); 2025-06-14 loss vs Edmen Shahbazyan (U-DEC)
- independent model votes for Mantas Kondratavicius: logistic 82.2%, calibrated GBM 75.4%. Their spread is a sensitivity check, not a confidence interval.

| Pre-fight evidence | Mantas Kondratavicius | Andre Petroski |
|---|---:|---:|
| Age | 27.31 | 35.41 |
| Reach (cm) | 190.50 | 185.42 |
| UFC fights | 1.00 | 13.00 |
| Days since UFC fight | 231.00 | 175.00 |
| Last 3: sig. strikes landed/min | 5.00 | 2.09 |
| Last 3: sig. strikes absorbed/min | 1.13 | 4.61 |
| Last 5: takedowns/15 min | 2.00 | 1.68 |
| Last 5: takedown defense (fraction) | 0.92 | 0.92 |
| Last 5: control-time fraction | 0.41 | 0.22 |
| Last 5: opponent pre-fight Elo | 1401.67 | 1506.39 |

- skill-only research model P(Mantas Kondratavicius) = 0.768; vig-free market = 0.726 (gap +0.042). Shipped number mixes both; deeper UFC history weights skill more.
- method: Mantas Kondratavicius by KO 35% / sub 11% / dec 23%; Andre Petroski by KO 7% / sub 5% / dec 20%
- pick outcome: Mantas Kondratavicius by KO/TKO, round 1 (method 35%; round given method 53%; exact outcome 18%)
- how it ends: finish 57% (R1 29% / R2 18% / R3 10%) vs. decision 43%
- likeliest endings: Mantas Kondratavicius by decision (23%), Andre Petroski by decision (20%), Mantas Kondratavicius by KO/TKO, round 1 (18%)
- drivers (log-odds): diff_strike_elo +0.34, diff_age +0.19, diff_opp_elo_l5 -0.09, diff_dec_win_rate -0.08, diff_grapple_elo -0.08

| ending | R1 | R2 | R3 | any round |
|---|---|---|---|---|
| Mantas Kondratavicius by KO/TKO | 18.3% | 10.8% | 5.6% | **34.7%** |
| Mantas Kondratavicius by submission | 5.4% | 3.5% | 1.9% | **10.7%** |
| Andre Petroski by KO/TKO | 3.3% | 2.1% | 1.2% | **6.7%** |
| Andre Petroski by submission | 2.1% | 1.5% | 0.9% | **4.5%** |
| decision (either fighter) | — | — | — | **43.4%** |

## Seokhyeon Ko vs. Wellington Turman — Welterweight
P(Seokhyeon Ko wins) = 0.780  ->  pick: Seokhyeon Ko (78%)
- research: Wrestling contrast: Seokhyeon Ko lands 3.3 takedowns/15 into Wellington Turman's 29% TDD.
- research: Form: Seokhyeon Ko holds the pre-fight-expectation-adjusted form edge (hot vs mixed over the last 5).
- research: Style record: Seokhyeon Ko is 67% against strikers in the UFC.
- recent fights, Seokhyeon Ko: 2026-07-18 loss vs Jean-Paul Lebosnoyani (U-DEC); 2025-11-01 win vs Phil Rowe (U-DEC); 2025-06-21 win vs Oban Elliott (U-DEC)
- recent fights, Wellington Turman: 2023-12-02 loss vs Jared Gooden (SUB); 2023-06-24 loss vs Randy Brown (U-DEC); 2022-11-12 loss vs Andre Petroski (U-DEC)
- independent model votes for Seokhyeon Ko: logistic 76.2%, calibrated GBM 78.5%. Their spread is a sensitivity check, not a confidence interval.

| Pre-fight evidence | Seokhyeon Ko | Wellington Turman |
|---|---:|---:|
| Age | 33.12 | 30.29 |
| Reach (cm) | 180.34 | 182.88 |
| UFC fights | 3.00 | 9.00 |
| Days since UFC fight | 112.00 | 1071.00 |
| Last 3: sig. strikes landed/min | 3.00 | 3.68 |
| Last 3: sig. strikes absorbed/min | 1.47 | 4.39 |
| Last 5: takedowns/15 min | 3.33 | 1.04 |
| Last 5: takedown defense (fraction) | 0.50 | 0.29 |
| Last 5: control-time fraction | 0.56 | 0.20 |
| Last 5: opponent pre-fight Elo | 1572.45 | 1540.65 |

- method: Seokhyeon Ko by KO 21% / sub 11% / dec 46%; Wellington Turman by KO 5% / sub 7% / dec 10%
- pick outcome: Seokhyeon Ko by decision (46%)
- how it ends: finish 44% (R1 23% / R2 14% / R3 7%) vs. decision 56%
- likeliest endings: Seokhyeon Ko by decision (46%), Seokhyeon Ko by KO/TKO, round 1 (11%), Wellington Turman by decision (10%)
- drivers (log-odds): diff_strike_elo +0.36, diff_elo +0.15, diff_age -0.13, diff_td15_l5 +0.10, diff_opp_elo_l5 +0.09

| ending | R1 | R2 | R3 | any round |
|---|---|---|---|---|
| Seokhyeon Ko by KO/TKO | 11.1% | 6.5% | 3.2% | **20.8%** |
| Seokhyeon Ko by submission | 5.6% | 3.6% | 1.8% | **11.1%** |
| Wellington Turman by KO/TKO | 2.6% | 1.6% | 0.8% | **5.0%** |
| Wellington Turman by submission | 3.4% | 2.4% | 1.2% | **7.0%** |
| decision (either fighter) | — | — | — | **56.1%** |

## Jonny Parsons vs. Jose Souza — Welterweight
P(Jonny Parsons wins) = 0.437  ->  pick: Jose Souza (56%; close fight)
- research: Style: both profile as strikers — a same-look fight.
- research: Pace: Jonny Parsons is the volume striker (6.3 vs 4.8 SLpM).
- research: Last fights: Jonny Parsons won last time out; Jose Souza won last time out.
- recent fights, Jonny Parsons: 2023-07-22 win vs Danny Roberts (KO/TKO); 2021-10-19 win vs Solomon Renfro (DEC); 2021-06-11 win vs Ricardo Chavez (KO/TKO)
- recent fights, Jose Souza: 2026-05-30 win vs Ding Meng (S-DEC)
- independent model votes for Jonny Parsons: logistic 65.4%, calibrated GBM 66.5%. Their spread is a sensitivity check, not a confidence interval.

| Pre-fight evidence | Jonny Parsons | Jose Souza |
|---|---:|---:|
| Age | 35.17 | unavailable |
| Reach (cm) | 175.26 | unavailable |
| UFC fights | 1.00 | 1.00 |
| Days since UFC fight | 1204.00 | 161.00 |
| Last 3: sig. strikes landed/min | 6.33 | 4.80 |
| Last 3: sig. strikes absorbed/min | 4.42 | 4.20 |
| Last 5: takedowns/15 min | 0.00 | 0.00 |
| Last 5: takedown defense (fraction) | 1.00 | unavailable |
| Last 5: control-time fraction | 0.14 | 0.00 |
| Last 5: opponent pre-fight Elo | 1532.84 | 1500.00 |

- skill-only research model P(Jonny Parsons) = 0.663; vig-free market = 0.372 (gap +0.290). Shipped number mixes both; deeper UFC history weights skill more.
- method: Jonny Parsons by KO 18% / sub 4% / dec 22%; Jose Souza by KO 27% / sub 10% / dec 20%
- pick outcome: Jose Souza by KO/TKO, round 1 (method 27%; round given method 57%; exact outcome 15%)
- how it ends: finish 58% (R1 32% / R2 17% / R3 9%) vs. decision 42%
- likeliest endings: Jonny Parsons by decision (22%), Jose Souza by decision (20%), Jose Souza by KO/TKO, round 1 (15%)
- drivers (log-odds): f2_reach_cm +0.38, diff_height_cm -0.31, f1_reach_cm +0.25, diff_style_reach_striker +0.11, diff_opp_elo_l5 +0.10

| ending | R1 | R2 | R3 | any round |
|---|---|---|---|---|
| Jonny Parsons by KO/TKO | 9.5% | 5.3% | 2.9% | **17.7%** |
| Jonny Parsons by submission | 1.9% | 1.1% | 0.6% | **3.6%** |
| Jose Souza by KO/TKO | 15.3% | 7.8% | 3.6% | **26.7%** |
| Jose Souza by submission | 5.4% | 3.0% | 1.4% | **9.8%** |
| decision (either fighter) | — | — | — | **42.3%** |

---
*Simulation/educational project. No betting advice. The market knows more than this model.*