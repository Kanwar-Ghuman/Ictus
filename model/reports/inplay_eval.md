# Between-rounds model evaluation

Predicts the winner during the break after round k from the pre-fight prior plus
cumulative fight stats that ESPN also reports live. Accuracy here is NOT trading
profit: Kalshi's in-play price also watches the fight, and no historical in-play
Kalshi prices exist to compare against. Profitability needs forward paper trading.

## Protocol

- Train: closing-line prior, before 2022-01-01 (3857 rows).
- Validation: closing-line prior, 2022–2023 (993 rows); selects C only.
- Test: skill-model prior, 2024+ (2018 rows); reported once.
- Selected C = 0.03 (validation log loss by C: 0.01: 0.5239, 0.03: 0.5227, 0.1: 0.5227, 0.3: 0.5233, 1.0: 0.5236).
- Saved artifact refit on 4850 closing-line rows through 2023.

## Results (prior only → with fight stats)

| split | after round | n | log loss | Brier | accuracy | ECE |
|---|---|---:|---|---|---|---|
| valid (p_market) | all | 993 | 0.6253 → **0.5227** | 0.2179 → 0.1707 | 65.8% → 74.8% | 0.036 → 0.047 |
| valid (p_market) | 1 | 515 | 0.6076 → **0.5557** | 0.2099 → 0.1867 | 67.8% → 71.5% | 0.044 → 0.060 |
| valid (p_market) | 2 | 395 | 0.6154 → **0.4296** | 0.2133 → 0.1382 | 67.3% → 81.3% | 0.050 → 0.053 |
| valid (p_market) | 3 | 44 | 0.7915 → **0.7426** | 0.2920 → 0.2250 | 45.5% → 63.6% | 0.225 → 0.228 |
| valid (p_market) | 4 | 39 | 0.7726 → **0.7805** | 0.2860 → 0.2284 | 46.2% → 66.7% | 0.215 → 0.181 |
| test (p_skill) | all | 2018 | 0.6428 → **0.4997** | 0.2257 → 0.1665 | 62.8% → 75.4% | 0.037 → 0.033 |
| test (p_skill) | 1 | 1043 | 0.6402 → **0.5754** | 0.2246 → 0.1959 | 62.8% → 70.0% | 0.037 → 0.040 |
| test (p_skill) | 2 | 830 | 0.6418 → **0.4454** | 0.2252 → 0.1444 | 63.0% → 79.6% | 0.036 → 0.037 |
| test (p_skill) | 3 | 77 | 0.6732 → **0.3306** | 0.2392 → 0.1053 | 61.0% → 87.0% | 0.066 → 0.106 |
| test (p_skill) | 4 | 68 | 0.6617 → **0.1919** | 0.2340 → 0.0551 | 63.2% → 94.1% | 0.063 → 0.068 |

Rounds 3–4 exist only for five-round fights; their samples are small.

## Coefficients (scaled features)

| feature | weight |
|---|---:|
| prior | +0.522 |
| prior_x_frac | -0.111 |
| sig_l | +0.232 |
| sig_a | -0.047 |
| head_l | +0.241 |
| body_l | +0.129 |
| leg_l | +0.004 |
| tot_l | +0.139 |
| td_l | +0.236 |
| td_a | -0.026 |
| kd | -0.050 |
| sub | -0.003 |
| ctrl | +0.034 |
| sig_l_x_frac | +0.100 |
| sig_a_x_frac | -0.087 |
| head_l_x_frac | +0.124 |
| body_l_x_frac | -0.006 |
| leg_l_x_frac | +0.020 |
| tot_l_x_frac | +0.046 |
| td_l_x_frac | -0.022 |
| td_a_x_frac | -0.082 |
| kd_x_frac | +0.101 |
| sub_x_frac | +0.065 |
| ctrl_x_frac | +0.188 |
