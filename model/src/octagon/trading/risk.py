"""Conservative, deterministic buy-only sizing in dollars (never binary floats)."""

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, InvalidOperation

ZERO = Decimal("0")
ONE = Decimal("1")
CENT = Decimal("0.01")


def decimal(value: object) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Expected a finite decimal number") from exc
    if not result.is_finite():
        raise ValueError("Expected a finite decimal number")
    return result


def money(value: object) -> Decimal:
    result = decimal(value)
    if result < ZERO or result != result.quantize(CENT):
        raise ValueError("Amount must be nonnegative dollars with at most two decimal places")
    return result


@dataclass(frozen=True)
class RiskPolicy:
    # These are policy haircuts, NOT statistical confidence intervals.
    probability_haircut: Decimal = Decimal("0.05")
    min_net_edge: Decimal = Decimal("0.04")
    kelly_fraction: Decimal = Decimal("0.25")
    max_order_fraction: Decimal = Decimal("0.05")
    max_bout_fraction: Decimal = Decimal("0.10")
    max_spread: Decimal = Decimal("0.08")
    max_contracts: int = 1000
    max_feed_age_seconds: float = 10.0
    max_source_age_seconds: float = 15.0
    max_book_age_seconds: float = 5.0
    close_buffer_seconds: float = 60.0
    # In-fight: let ESPN settle round totals after the break begins.
    min_break_seconds: float = 10.0
    # ESPN keeps showing the break ~30 s into the next round; stay inside the real 60 s.
    max_break_seconds: float = 40.0
    prefight_capture_seconds: float = 10.0
    prefight_max_age_seconds: float = 6 * 3600.0


@dataclass(frozen=True)
class Candidate:
    side: str
    probability: Decimal
    price: Decimal
    count: int
    reserved_cost: Decimal
    estimated_cost: Decimal
    net_edge: Decimal


def taker_fee(price: Decimal, count: int, multiplier: Decimal) -> Decimal:
    """Conservative cent-rounded quadratic taker fee; fee overrides are required.

    The exchange may charge finer precision or apply rounding rebates. Do not
    spend those rebates or assume the displayed quote will actually fill.
    """
    return (Decimal("0.07") * multiplier * count * price * (ONE - price)).quantize(
        CENT, rounding=ROUND_CEILING
    )


def size_candidate(
    *,
    side: str,
    probability: Decimal,
    price: Decimal,
    depth: Decimal,
    spread: Decimal,
    budget: Decimal,
    remaining: Decimal,
    bout_spent: Decimal,
    fee_multiplier: Decimal,
    policy: RiskPolicy,
) -> Candidate | None:
    """Buy only at displayed executable depth; never force spending a budget."""
    values = (probability, price, depth, spread, budget, remaining, bout_spent, fee_multiplier)
    if any(not v.is_finite() for v in values):
        return None
    if side not in {"yes", "no"} or not ZERO < probability < ONE or not ZERO < price < ONE:
        return None
    if min(depth, budget, remaining, fee_multiplier) <= ZERO or bout_spent < ZERO:
        return None
    if not ZERO <= spread <= policy.max_spread:
        return None
    # Reserve a cent-rounded fee for *each* contract: splitting fills must not
    # exceed the reservation due to exchange fee rounding.
    unit_cost = price + taker_fee(price, 1, fee_multiplier)
    conservative_p = max(ZERO, probability - policy.probability_haircut)
    edge = conservative_p - unit_cost
    if unit_cost >= ONE or edge < policy.min_net_edge:
        return None
    kelly = max(ZERO, edge / (ONE - unit_cost)) * policy.kelly_fraction
    allowance = min(
        remaining,
        budget * policy.max_order_fraction,
        max(ZERO, budget * policy.max_bout_fraction - bout_spent),
        budget * kelly,
    )
    count = min(
        policy.max_contracts,
        int(depth.to_integral_value(rounding=ROUND_FLOOR)),
        int((allowance / unit_cost).to_integral_value(rounding=ROUND_FLOOR)),
    )
    if count < 1:
        return None
    return Candidate(
        side, probability, price, count, unit_cost * count,
        price * count + taker_fee(price, count, fee_multiplier), edge,
    )
