"""Trades the bot refuses even when the model sees an edge.

Each check returns a plain reason, or None to let the order through. They come
from the first real-money night with in-fight trading (November 7, 2026) and
the validation backtest:

* Longshots. Every contract bought under 20 cents that night lost, and the
  model's sub-20-cent buys returned -52% on the priced validation fights.
* Falling prices. Mid-round the bot bought one fighter eight times in two
  minutes while her price went from 16 cents to 5. ESPN's stats trail the
  broadcast, so a price that is sliding is information the model lacks.
* Both sides. Buying the other fighter after one is held only pays the fee
  and the spread twice.
"""

from __future__ import annotations

from collections import defaultdict, deque
from decimal import Decimal

from octagon.trading.risk import RiskPolicy, decimal

FILLED = frozenset({"filled", "demo_filled", "paper_filled"})
OTHER_SIDE = {"yes": "no", "no": "yes"}


class PriceTape:
    """Recent asks per market, so a buy can see where the price came from."""

    def __init__(self, keep_seconds: float):
        self.keep_seconds = keep_seconds
        self._ticks: dict[str, deque[tuple[float, Decimal, Decimal]]] = defaultdict(deque)

    def add(self, ticker: str, now: float, yes_ask: Decimal, no_ask: Decimal) -> None:
        ticks = self._ticks[ticker]
        ticks.append((now, yes_ask, no_ask))
        while ticks and now - ticks[0][0] > self.keep_seconds:
            ticks.popleft()

    def last_sample(self, ticker: str) -> float | None:
        ticks = self._ticks.get(ticker)
        return ticks[-1][0] if ticks else None

    def watched_seconds(self, ticker: str, now: float) -> float:
        ticks = self._ticks.get(ticker)
        return now - ticks[0][0] if ticks else 0.0

    def high(self, ticker: str, side: str, now: float, window: float) -> Decimal | None:
        """Highest ask for ``side`` inside the last ``window`` seconds."""
        index = 1 if side == "yes" else 2
        asks = [tick[index] for tick in self._ticks.get(ticker, ()) if now - tick[0] <= window]
        return max(asks) if asks else None


def longshot_reason(price: Decimal, policy: RiskPolicy) -> str | None:
    if price < policy.min_price:
        return f"Longshot: {price * 100:.0f}¢ is under the {policy.min_price * 100:.0f}¢ floor"
    return None


def falling_price_reason(tape: PriceTape, ticker: str, side: str, price: Decimal,
                         now: float, policy: RiskPolicy, *, mid_round: bool) -> str | None:
    """In-fight only. A break has settled stats, so it needs no watching period."""
    if mid_round and tape.watched_seconds(ticker, now) < policy.min_price_watch_seconds:
        return "Watching the live price before buying"
    high = tape.high(ticker, side, now, policy.price_window_seconds)
    if high is not None and high - price >= policy.max_price_drop:
        return (f"Price is falling fast: {high * 100:.0f}¢ to {price * 100:.0f}¢ "
                f"in {policy.price_window_seconds:.0f}s")
    return None


def held_side(orders: list[dict], ticker: str) -> str | None:
    """The side of this market the session already owns, if any.

    With fills on both sides (possible only in journals older than this rule)
    the larger position wins.
    """
    owned = {"yes": Decimal(0), "no": Decimal(0)}
    for order in orders:
        if order.get("ticker") != ticker or order.get("status") not in FILLED:
            continue
        if order.get("side") in owned:
            owned[order["side"]] += decimal(order.get("filled_count") or 0)
    if not any(owned.values()):
        return None
    return max(owned, key=lambda side: owned[side])
