"""The probability a pre-fight order is allowed to bet.

The fitted stack from the train-era priced fights is a = 1.00 on the vig-free
line and b = 0.29 on the skill logit (evaluation_valid.md). It is not retuned
here. Research-weight mixing stays on the written card and out of this path.
"""

from __future__ import annotations

from decimal import Decimal

import numpy as np

from octagon.models.market import predict_stack
from octagon.trading.risk import decimal

# Train-era out-of-sample fit. Do not refit these on 2022–2023 or the test era.
STACK_A = 1.0
STACK_B = 0.29


def pure_stack(p_skill: Decimal, p_market: Decimal) -> Decimal:
    """sigmoid(1.00 * logit(market) + 0.29 * logit(skill)), six decimal places."""
    if not 0 < p_skill < 1 or not 0 < p_market < 1:
        raise ValueError("Stack inputs must be probabilities strictly between 0 and 1")
    raw = predict_stack(
        STACK_A, STACK_B, np.asarray([float(p_market)]), np.asarray([float(p_skill)]),
    )
    p = float(raw[0])
    if not 0 < p < 1:
        raise ValueError("Stack probability out of range")
    return decimal(f"{p:.6f}")


def lag_block_reason(
    stack: Decimal,
    sportsbook: Decimal,
    ask: Decimal,
    spread: Decimal,
    fee: Decimal,
    *,
    min_lag: Decimal,
    max_gap: Decimal,
) -> str | None:
    """Why this ask is not a slow-venue buy, or None when it is.

    The sportsbook has to be richer than the Kalshi ask by the taker fee, half
    the spread, and ``min_lag``. The stack has to stay within ``max_gap`` of
    the sportsbook, so a broken book cannot drag an order.
    """
    if abs(stack - sportsbook) > max_gap:
        return "Stack and sportsbook disagree by more than 8¢"
    if sportsbook - ask - fee - spread / 2 <= min_lag:
        return "Kalshi is not lagging the sportsbook by the fee, half the spread, and 2¢"
    return None

