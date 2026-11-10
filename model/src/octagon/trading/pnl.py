"""What a session's bets have paid back so far.

A $1 contract pays $1 when its fighter wins, nothing when the other fighter
wins, and 50 cents on a draw or no-contest. Results come from the ESPN feed,
so this is the bot's own tally: Kalshi's settlement is the record that counts.
Paper fills are simulations and are tallied the same way for practice nights.
"""

from __future__ import annotations

import re
from decimal import Decimal

from octagon.trading.guards import FILLED
from octagon.trading.names import same_name
from octagon.trading.risk import decimal

HALF = Decimal("0.5")
CENT = Decimal("0.01")
SPLIT_RESULT = re.compile(r"draw|no contest", re.IGNORECASE)


def corner_names(bout: dict) -> tuple[str, str]:
    """ESPN's names for (fighter_a, fighter_b)."""
    return (str((bout.get("fighter_a") or {}).get("name", "")),
            str((bout.get("fighter_b") or {}).get("name", "")))


def card_winner(bout: dict, f1: str, f2: str, f1_is_a: bool) -> str | None:
    """The winner ESPN reports, under the name the card uses for that fighter."""
    won = [bool((bout.get(key) or {}).get("winner")) for key in ("fighter_a", "fighter_b")]
    named = bout.get("winner")
    if won[0] == won[1] and isinstance(named, str) and named:
        won = [same_name(named, corner) for corner in corner_names(bout)]
    if won[0] == won[1]:
        return None
    return f1 if won[0] == f1_is_a else f2


def bout_result(bout: dict, winner: str | None) -> dict | None:
    """A decided bout's result: the winner (a card name), a 50-cent split, or None.

    ``winner`` is the caller's reading of who won, already under the card's
    name for that fighter. A final bout with no winner counts as a split only
    when ESPN's method says draw or no-contest, never because a flag is late.
    """
    if not isinstance(bout, dict) or bout.get("status") != "final":
        return None
    if winner:
        return {"winner": winner}
    if SPLIT_RESULT.search(str(bout.get("method") or "")):
        return {"split": True}
    return None


def session_results(orders: list[dict], mappings: list[dict],
                    results: dict[str, dict]) -> dict:
    """Totals in dollars, plus each market's outcome for the dashboard."""
    by_ticker = {m["ticker"]: m for m in mappings}
    settled_cost = returned = open_cost = open_payout = Decimal(0)
    markets: dict[str, dict] = {}
    for order in orders:
        mapping = by_ticker.get(order.get("ticker"))
        contracts = decimal(order.get("filled_count") or 0)
        if mapping is None or order.get("status") not in FILLED or contracts <= 0:
            continue
        cost = decimal(order["cost_dollars"])
        fighter = _side_fighter(mapping, order["side"])
        result = results.get(mapping["bout_id"])
        market = markets.setdefault(mapping["ticker"], {
            "fighter": fighter, "outcome": "open", "cost_dollars": Decimal(0),
            "returned_dollars": Decimal(0), "contracts": Decimal(0)})
        market["cost_dollars"] += cost
        market["contracts"] += contracts
        if result is None:
            open_cost += cost
            open_payout += contracts
            continue
        if result.get("split"):
            paid, outcome = contracts * HALF, "split"
        elif same_name(result["winner"], fighter):
            paid, outcome = contracts, "won"
        else:
            paid, outcome = Decimal(0), "lost"
        settled_cost += cost
        returned += paid
        market["returned_dollars"] += paid
        # A market can hold both fighters only in journals older than the
        # one-side rule; then it is "won" if anything on it paid.
        if market["outcome"] in {"open", "lost"}:
            market["outcome"] = outcome

    def text(amount: Decimal) -> str:
        return str(amount.quantize(CENT))

    return {
        "settled_cost_dollars": text(settled_cost), "returned_dollars": text(returned),
        "profit_dollars": text(returned - settled_cost),
        "open_cost_dollars": text(open_cost), "open_payout_dollars": text(open_payout),
        "markets": {ticker: {key: text(value) if isinstance(value, Decimal) else value
                             for key, value in market.items()}
                    for ticker, market in markets.items()},
    }


def _side_fighter(mapping: dict, side: str) -> str:
    yes, f1, f2 = mapping["yes_fighter"], mapping["f1"], mapping["f2"]
    return yes if side == "yes" else (f2 if yes == f1 else f1)
