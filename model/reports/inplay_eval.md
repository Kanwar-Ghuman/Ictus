# Between-rounds model evaluation

Predicts the winner during the break after round k from the pre-fight prior plus
cumulative fight stats that ESPN also reports live. Accuracy here is NOT trading
profit: Kalshi's in-play price also watches the fight, and no historical in-play
Kalshi prices exist to compare against. Profitability needs forward paper trading.

## Protocol

- Train: closing-line prior, before 2022-01-01 (3857 rows).
- Validation: closing-line prior, 2022–2023 (993 rows); selects C, then the three-round slope.
- Test: skill-model prior, 2024+ (2137 rows); reported once.
- Selected C = 0.03 (validation log loss by C: 0.01: 0.5239, 0.03: 0.5227, 0.1: 0.5227, 0.3: 0.5233, 1.0: 0.5236).
- Saved artifact refit on 4850 closing-line rows through 2023.

## Results (prior only → with fight stats)

| split | after round | n | log loss | Brier | accuracy | ECE |
|---|---|---:|---|---|---|---|
| valid (p_market) | all | 993 | 0.6253 → **0.5167** | 0.2179 → 0.1684 | 65.8% → 74.8% | 0.036 → 0.043 |
| valid (p_market) | 1 | 515 | 0.6076 → **0.5513** | 0.2099 → 0.1844 | 67.8% → 71.5% | 0.044 → 0.050 |
| valid (p_market) | 2 | 395 | 0.6154 → **0.4204** | 0.2133 → 0.1354 | 67.3% → 81.3% | 0.050 → 0.037 |
| valid (p_market) | 3 | 44 | 0.7915 → **0.7426** | 0.2920 → 0.2250 | 45.5% → 63.6% | 0.225 → 0.228 |
| valid (p_market) | 4 | 39 | 0.7726 → **0.7805** | 0.2860 → 0.2284 | 46.2% → 66.7% | 0.215 → 0.181 |
| test (p_skill) | all | 2137 | 0.6449 → **0.5070** | 0.2265 → 0.1690 | 63.2% → 74.6% | 0.037 → 0.030 |
| test (p_skill) | 1 | 1105 | 0.6431 → **0.5797** | 0.2257 → 0.1976 | 63.5% → 69.0% | 0.034 → 0.043 |
| test (p_skill) | 2 | 877 | 0.6428 → **0.4490** | 0.2255 → 0.1459 | 63.6% → 79.1% | 0.043 → 0.029 |
| test (p_skill) | 3 | 82 | 0.6734 → **0.3536** | 0.2394 → 0.1144 | 58.5% → 85.4% | 0.117 → 0.077 |
| test (p_skill) | 4 | 73 | 0.6647 → **0.2765** | 0.2357 → 0.0758 | 58.9% → 91.8% | 0.116 → 0.080 |

Rounds 3–4 exist only for five-round fights; their samples are small.
The validation rows also chose the slope, so read calibration on the test rows.

## Confidence slope

The raw logit is too timid in three-round fights: the fighter it puts at 25% wins
about 20% of the time. One multiplier on the logit, fit on validation, fixes that.
Five-round fights are left at 1.0: too few rows, and their slope flips between eras.

Slopes: 3 rounds × 1.315.

| three-round test fights | n | log loss | Brier | ECE |
|---|---:|---|---|---|
| raw | 1755 | 0.5154 | 0.1723 | 0.031 |
| with slope | 1755 | 0.5147 | 0.1717 | 0.032 |

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
