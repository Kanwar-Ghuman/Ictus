"""Deterministic buy-only sizing in dollars (never binary floats).

Budget use is card-wide: every fight still to be decided gets an equal slice of
the money left for its phase, and a fight's bet is its slice scaled by how
strong the edge is (its Kelly fraction relative to ``full_slice_kelly``). Money
from fights the bot passes on flows to the fights that are left.
"""

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
    # Optional extra margin subtracted from the model probability (0 = trust it).
    probability_haircut: Decimal = Decimal("0")
    # Minimum expected profit per $1 contract after the reserved taker fee.
    min_net_edge: Decimal = Decimal("0.03")
    # A bet with this Kelly fraction gets exactly one slice; stronger edges get
    # more, up to max_slice_multiple slices.
    full_slice_kelly: Decimal = Decimal("0.10")
    max_slice_multiple: Decimal = Decimal("2")
    # Hard ceiling on all spending on one fight (every phase), share of budget.
    max_bout_fraction: Decimal = Decimal("0.40")
    # With in-fight trading on, pre-fight bets may use at most 1 - this share.
    inplay_reserve: Decimal = Decimal("0.30")
    # A missed or partly filled order is retried while the edge lasts.
    max_prefight_attempts: int = 6
    prefight_retry_seconds: float = 30.0
    max_break_attempts: int = 3
    break_retry_seconds: float = 4.0
    # Live rounds reprice off the clock and can buy again while the edge lasts.
    max_live_attempts: int = 12
    live_retry_seconds: float = 1.0
    # Both fighters need this many UFC fights for skill-model forecasts (0 = allow debuts).
    min_ufc_fights: int = 1
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


def edge_of(probability: Decimal, price: Decimal, fee_multiplier: Decimal,
            policy: RiskPolicy) -> tuple[Decimal, Decimal, Decimal]:
    """(per-contract cost incl. fee, net edge, Kelly fraction) for buying at price."""
    # Reserve a cent-rounded fee for *each* contract: splitting fills must not
    # exceed the reservation due to exchange fee rounding.
    unit_cost = price + taker_fee(price, 1, fee_multiplier)
    edge = max(ZERO, probability - policy.probability_haircut) - unit_cost
    kelly = max(ZERO, edge / (ONE - unit_cost)) if unit_cost < ONE else ZERO
    return unit_cost, edge, kelly


def bout_allowance(*, kelly: Decimal, budget: Decimal, remaining: Decimal,
                   phase_available: Decimal, phase_pool: Decimal, open_bouts: int,
                   phase_bout_spent: Decimal, bout_spent: Decimal,
                   policy: RiskPolicy, unit_cost: Decimal = ZERO) -> Decimal:
    """Dollars this fight may still use now.

    phase_pool: money for fights still open in this phase (unspent phase money
    plus what this phase already put on those open fights), split evenly.
    A fight with an edge and nothing on it yet in this phase may always buy one
    contract, so small budgets spread over long cards still trade.
    """
    if open_bouts < 1 or kelly <= ZERO:
        return ZERO
    conviction = min(policy.max_slice_multiple, kelly / policy.full_slice_kelly)
    target = phase_pool / open_bouts * conviction
    if phase_bout_spent <= ZERO:
        target = max(target, unit_cost)
    return max(ZERO, min(
        remaining,
        phase_available,
        budget * policy.max_bout_fraction - bout_spent,
        target - phase_bout_spent,
    ))


def size_candidate(
    *,
    side: str,
    probability: Decimal,
    price: Decimal,
    depth: Decimal,
    spread: Decimal,
    allowance: Decimal,
    fee_multiplier: Decimal,
    policy: RiskPolicy,
) -> Candidate | None:
    """Buy only at displayed executable depth, within the dollar allowance."""
    values = (probability, price, depth, spread, allowance, fee_multiplier)
    if any(not v.is_finite() for v in values):
        return None
    if side not in {"yes", "no"} or not ZERO < probability < ONE or not ZERO < price < ONE:
        return None
    if min(depth, allowance, fee_multiplier) <= ZERO:
        return None
    if not ZERO <= spread <= policy.max_spread:
        return None
    unit_cost, edge, _ = edge_of(probability, price, fee_multiplier, policy)
    if unit_cost >= ONE or edge < policy.min_net_edge:
        return None
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
