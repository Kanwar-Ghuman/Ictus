"""The one probability the bot bets, before and during a fight.

It is the sportsbook line with a small push from the skill model:

    logit(p) = 1.00 * logit(line) + 0.29 * logit(skill)

The weights were fit on train-era priced fights and are not retuned here. On
the 697 priced validation fights this stack is the only layer that beat the
vig-free line (log loss 0.6010 against 0.6035), and its 3-cent bets were the
only ones that returned a profit against that line. The skill number alone
lost, most of all on longshots. See docs/kalshi_trading.md.

The line is the moneyline ESPN streams with the fight, read at trade time.
The odds saved on the card are the fallback. With neither, there is no
pre-fight order.
"""

from __future__ import annotations

import math
from decimal import Decimal

import numpy as np

from octagon.betting.odds import american_to_decimal, implied_probability, remove_vig
from octagon.models.market import predict_stack
from octagon.trading.risk import decimal

# Train-era out-of-sample fit. Do not refit these on 2022–2023 or the test era.
STACK_A = 1.0
STACK_B = 0.29
# A two-way book prices in at most this much margin. More is a stale or
# one-sided quote, not a line.
MAX_OVERROUND = 1.15


def pure_stack(p_skill: Decimal, p_line: Decimal) -> Decimal:
    """sigmoid(1.00 * logit(line) + 0.29 * logit(skill)), six decimal places."""
    if not 0 < p_skill < 1 or not 0 < p_line < 1:
        raise ValueError("Stack inputs must be probabilities strictly between 0 and 1")
    raw = predict_stack(
        STACK_A, STACK_B, np.asarray([float(p_line)]), np.asarray([float(p_skill)]),
    )
    p = float(raw[0])
    if not 0 < p < 1:
        raise ValueError("Stack probability out of range")
    return decimal(f"{p:.6f}")


def moneyline_probability(odds_1: object, odds_2: object) -> Decimal | None:
    """Vig-free P(fighter 1 wins) from two American moneylines, or None.

    Accepts the strings ESPN sends ("-205", "+170", "EVEN"). Anything missing,
    malformed, or priced with an implausible margin gives None.
    """
    try:
        decimals = [american_to_decimal(_american(text)) for text in (odds_1, odds_2)]
        implied = [implied_probability(value) for value in decimals]
    except (TypeError, ValueError):
        return None
    if not 1.0 <= sum(implied) <= MAX_OVERROUND:
        return None
    fair, _ = remove_vig(*implied)
    return decimal(f"{fair:.6f}") if 0 < fair < 1 else None


def _american(text: object) -> float:
    if not isinstance(text, str):
        raise TypeError("Moneyline must be text")
    cleaned = text.strip().upper()
    if cleaned in {"EVEN", "EV", "PK"}:
        return 100.0
    value = float(cleaned)
    if not math.isfinite(value) or abs(value) < 100:
        raise ValueError("Not an American moneyline")
    return value


def order_probability(p_skill: Decimal, live_line: Decimal | None,
                      card_line: Decimal | None) -> tuple[Decimal, str] | None:
    """(P(fighter 1 wins), line source) for an order, or None with no line."""
    for line, source in ((live_line, "live sportsbook line"), (card_line, "card line")):
        if line is not None:
            return pure_stack(p_skill, line), source
    return None


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
