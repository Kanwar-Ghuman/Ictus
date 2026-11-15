"""Whole fight nights, randomized, with the rules that must never break.

Each night runs a paper session through every fight on a card: scheduled, live
rounds with a ticking clock and growing stats, the breaks between them, and a
result. Kalshi prices wander and sometimes collapse mid-round. After every
decision the session is checked against the bot's hard promises.
"""

import random
import time
from decimal import Decimal as D

import pytest

from octagon.inplay.model import FEATURES, InplayModel
from octagon.trading.engine import TradingEngine
from octagon.trading.guards import FILLED
from octagon.trading.kalshi import KalshiTransportError
from octagon.trading.ledger import Ledger
from octagon.trading.risk import RiskPolicy
from tests.test_trading import Exchange, iso

FIGHTS = 5
BUDGET = D("70.00")
STEP_SECONDS = 10
ROUND_SECONDS = 300


class Night:
    """A card, an exchange whose prices move, and a clock that can be skipped ahead."""

    def __init__(self, seed: int, tmp_path, monkeypatch, mode: str = "paper"):
        self.rng = random.Random(seed)
        self.skipped = 0.0
        real = time.monotonic
        monkeypatch.setattr(time, "monotonic", lambda: real() + self.skipped)

        self.bouts = []
        for index in range(FIGHTS):
            line = self.rng.uniform(0.12, 0.88)
            self.bouts.append({
                "f1": f"Red Corner{index}", "f2": f"Blue Corner{index}",
                "p_skill": min(0.95, max(0.05, line + self.rng.uniform(-0.2, 0.2))),
                "p_market": None if self.rng.random() < 0.15 else line,
                "f1_ufc_fights": 6, "f2_ufc_fights": 6, "scheduled_rounds": 3})
        # Kalshi's price for f1, per fight, in cents. It starts near the line.
        self.yes_cents = [int(min(95, max(5, b["p_skill"] * 100 + self.rng.uniform(-12, 12))))
                          for b in self.bouts]
        self.spread = [1] * FIGHTS
        self.status = ["scheduled"] * FIGHTS
        self.live = {}  # index -> {"round", "clock", "detail", "stats"}
        self.winner = [None] * FIGHTS
        self.asks: list[tuple[float, str, str, D]] = []  # (time, ticker, side, ask) seen at each quote

        self.exchange = Exchange()
        self.exchange.get_market = self._market
        self.exchange.get_orderbook = self._book
        coef = dict.fromkeys(FEATURES, 0.0)
        coef["prior"], coef["sig_l"], coef["ctrl"] = 1.0, 0.05, 0.3
        model = InplayModel(scale=dict.fromkeys(FEATURES, 1.0), coef=coef, meta={})
        # With real orders, an order Kalshi never received is released on the next pass.
        self.policy = RiskPolicy() if mode == "paper" else RiskPolicy(lost_order_seconds=0)
        self.engine = TradingEngine(Ledger(tmp_path / f"night{seed}.db"), self.exchange,
                                    inplay=model, policy=self.policy, mode=mode)
        self.engine.sleep = lambda seconds: None
        if mode != "paper":
            self._send = self.exchange.create_ioc_order
            self.exchange.create_ioc_order = self._unreliable_send
        self.engine.configure({
            "card_slug": "stress", "espn_event_id": "event-1", "budget_dollars": str(BUDGET),
            "mappings": [{"bout_id": str(i + 1), "ticker": f"WIN-{i}", "f1": b["f1"], "f2": b["f2"],
                          "yes_fighter": b["f1"], "confirmed": True}
                         for i, b in enumerate(self.bouts)],
        }, {"slug": "stress", "date": iso()[:10], "bouts": self.bouts})

    # -- the fake exchange ---------------------------------------------------

    def _market(self, ticker):
        bout = self.bouts[int(ticker.split("-")[-1])]
        return {"ticker": ticker, "market_type": "binary", "yes_sub_title": bout["f1"],
                "event_ticker": "KXUFCFIGHT-EVENT", "rules_primary": f'{bout["f1"]} vs {bout["f2"]}.',
                "occurrence_datetime": iso(3600), "status": "active", "open_time": iso(-3600),
                "close_time": iso(36000), "notional_value_dollars": "1.0000", "exchange_index": 0}

    def _book(self, ticker):
        index = int(ticker.split("-")[-1])
        yes_ask = self.yes_cents[index]
        yes_bid = max(1, yes_ask - self.spread[index])  # one book per instant, however often it is read
        now = time.monotonic()
        self.asks.append((now, ticker, "yes", D(yes_ask) / 100))
        self.asks.append((now, ticker, "no", D(100 - yes_bid) / 100))
        return {"orderbook_fp": {"yes_dollars": [[f"{yes_bid / 100:.4f}", "40.00"]],
                                 "no_dollars": [[f"{(100 - yes_ask) / 100:.4f}", "40.00"]]}}

    def _unreliable_send(self, ticker, side, price, count, client_order_id):
        """Kalshi on a bad night: lost requests, rejections, partial and empty fills."""
        roll = self.rng.random()
        self.exchange.partial_count = None
        if roll < 0.06:
            raise KalshiTransportError("timed out before Kalshi got it", ambiguous=True)
        if roll < 0.12:
            raise KalshiTransportError("rejected", status_code=400, ambiguous=False)
        if roll < 0.30:
            self.exchange.partial_count = D(self.rng.randint(0, count))
        result = self._send(ticker, side, price, count, client_order_id)
        if roll > 0.94:
            raise KalshiTransportError("timed out after Kalshi filled it", ambiguous=True)
        return result

    # -- the fake fight feed -------------------------------------------------

    def _corner(self, index, key):
        stats = self.live.get(index, {}).get("stats", {}).get(key)
        corner = {"name": self.bouts[index]["f1" if key == "a" else "f2"],
                  "winner": self.winner[index] == key, "odds": None}
        if stats:
            corner["stats"] = {
                "knockDowns": str(stats["kd"]), "totalStrikes": f'{stats["sig"]}/{stats["sig"] * 2 + 1}',
                "sigStrikes": f'{stats["sig"]}/{stats["sig"] * 2 + 1}',
                "headStrikes": f'{stats["sig"]}/{stats["sig"] * 2 + 1}', "bodyStrikes": "0/0",
                "legStrikes": "0/0", "timeInControl": f'{stats["ctrl"] // 60}:{stats["ctrl"] % 60:02d}',
                "takedowns": "0/0", "submissions": "0"}
        return corner

    def feed(self):
        data = []
        for index in range(FIGHTS):
            live = self.live.get(index, {})
            data.append({
                "bout_id": str(index + 1), "status": self.status[index],
                "status_detail": live.get("detail"), "round": live.get("round"),
                "clock": live.get("clock"), "method": "KO/TKO" if self.winner[index] else None,
                "winner": None, "fighter_a": self._corner(index, "a"),
                "fighter_b": self._corner(index, "b")})
        return {"success": True, "data": data,
                "meta": {"event_id": "event-1", "event_name": "Stress", "event_status": "in_progress",
                         "captured_at": iso(), "espn_updated_at": iso(), "seq": 1}}

    # -- one step of the night ----------------------------------------------

    def step(self, seconds=STEP_SECONDS):
        self.skipped += seconds
        for index in range(FIGHTS):
            if self.status[index] != "final":
                self.yes_cents[index] = int(min(97, max(3, self.yes_cents[index] + self.rng.randint(-2, 2))))
                self.spread[index] = self.rng.choice((1, 1, 2, 3))
        self.engine.update_feed(self.feed())
        self.engine.tick()
        check(self)

    def fight(self, index):
        """Run one bout from the opening bell to a result."""
        stats = {"a": {"sig": 0, "kd": 0, "ctrl": 0}, "b": {"sig": 0, "kd": 0, "ctrl": 0}}
        self.status[index] = "in_progress"
        ends_early = self.rng.random() < 0.4
        for round_k in (1, 2, 3):
            for elapsed in range(STEP_SECONDS, ROUND_SECONDS, STEP_SECONDS * 2):
                for key in ("a", "b"):
                    stats[key]["sig"] += self.rng.randint(0, 4)
                    stats[key]["ctrl"] += self.rng.choice((0, 0, 0, 20))
                left = ROUND_SECONDS - elapsed
                self.live[index] = {"round": round_k, "clock": f"{left // 60}:{left % 60:02d}",
                                    "detail": "STATUS_IN_PROGRESS", "stats": stats}
                if self.rng.random() < 0.06:
                    # Something happened that the stats have not caught up with.
                    self.yes_cents[index] = int(min(97, max(3, self.yes_cents[index]
                                                            + self.rng.choice((-25, -15, 15, 25)))))
                self.step(STEP_SECONDS * 2)
                if ends_early and round_k == 2 and elapsed > 150:
                    return self.finish(index)
            if round_k < 3:
                self.live[index] = {"round": round_k, "clock": "0:00",
                                    "detail": "STATUS_END_OF_ROUND", "stats": stats}
                for _ in range(4):
                    self.step()
        self.finish(index)

    def finish(self, index):
        self.winner[index] = "a" if self.rng.random() < self.yes_cents[index] / 100 else "b"
        self.status[index] = "final"
        self.live[index]["detail"] = "STATUS_FINAL"
        self.yes_cents[index] = 97 if self.winner[index] == "a" else 3
        self.step()

    def orders(self):
        return self.engine.ledger.orders(self.engine.session_id)


def check(night: Night):
    """The promises that hold after every single decision."""
    engine, policy = night.engine, night.policy
    assert engine.running.is_set(), engine.message
    orders = night.orders()
    spent = sum(D(o["cost_dollars"]) + D(o["reserved_dollars"]) for o in orders)
    assert spent <= BUDGET, "spent more than the limit"

    by_fight: dict[str, D] = {}
    sides: dict[str, set] = {}
    attempts: dict[tuple, int] = {}
    for order in orders:
        fight, *phase = order["bout_id"].split(":")
        by_fight[fight] = by_fight.get(fight, D(0)) + D(order["cost_dollars"]) + D(order["reserved_dollars"])
        kind = "pre" if not phase or phase[0].startswith("p") else phase[0]  # "r1", "l2" or "pre"
        attempts[(fight, kind)] = attempts.get((fight, kind), 0) + 1
        if order["status"] in FILLED:
            sides.setdefault(order["ticker"], set()).add(order["side"])
            assert D(order["price_dollars"]) >= policy.min_price, "bought a longshot"
    assert all(total <= BUDGET * policy.max_bout_fraction for total in by_fight.values()), \
        "one fight took more than its share"
    assert all(len(held) == 1 for held in sides.values()), "holds both fighters in one fight"
    for (fight, kind), count in attempts.items():
        limit = (policy.max_prefight_attempts if kind == "pre"
                 else policy.max_break_attempts if kind.startswith("r")
                 else policy.max_live_attempts)
        assert count <= limit, f"too many buys in {kind} of fight {fight}"


def falling_buys(night: Night) -> list[dict]:
    """Mid-fight buys of a side whose ask had dropped past the limit in the window before."""
    bad = []
    for decision_time, order in night.bought:
        if ":" not in order["bout_id"] or order["bout_id"].split(":")[1].startswith("p"):
            continue
        price = D(order["price_dollars"])
        window = [ask for at, ticker, side, ask in night.asks
                  if ticker == order["ticker"] and side == order["side"]
                  and 0 <= decision_time - at <= night.policy.price_window_seconds]
        if window and max(window) - price >= night.policy.max_price_drop:
            bad.append(order)
    return bad


def run_night(night: Night):
    """Drive a whole card and remember when each order appeared."""
    night.bought = []
    known = set()
    plain_step = night.step

    def tracking_step(seconds=STEP_SECONDS):
        plain_step(seconds)
        for order in night.orders():
            if order["id"] not in known:
                known.add(order["id"])
                night.bought.append((time.monotonic(), order))

    night.step = tracking_step
    night.engine.update_feed(night.feed())
    night.engine.start()
    for _ in range(6):  # the hour before the first fight
        night.step(60)
    for index in range(FIGHTS):
        night.fight(index)
        night.step(120)  # the walkouts before the next one
    check(night)


def settled_tally(night: Night) -> dict:
    """Every fight is over, so nothing is still riding and the sums agree."""
    results = night.engine.status()["results"]
    assert D(results["open_cost_dollars"]) == 0
    assert D(results["profit_dollars"]) == D(results["returned_dollars"]) - D(results["settled_cost_dollars"])
    assert all(market["outcome"] in {"won", "lost"} for market in results["markets"].values())
    return results


@pytest.mark.parametrize("seed", range(12))
def test_a_whole_fight_night_never_breaks_a_promise(seed, tmp_path, monkeypatch):
    night = Night(seed, tmp_path, monkeypatch)
    run_night(night)
    assert not falling_buys(night), "bought into a falling price mid-fight"
    assert all(order["status"] == "paper_filled" for order in night.orders())
    settled_tally(night)


@pytest.mark.parametrize("seed", range(100, 108))
def test_real_orders_stay_consistent_when_kalshi_misbehaves(seed, tmp_path, monkeypatch):
    """The real order path, with lost requests, rejections, and partial fills thrown in."""
    night = Night(seed, tmp_path, monkeypatch, mode="demo")
    run_night(night)
    assert not falling_buys(night), "bought into a falling price mid-fight"
    orders = night.orders()
    # Nothing is left hanging: every order ended filled, unfilled or rejected.
    assert {order["status"] for order in orders} <= {"demo_filled", "unfilled", "rejected"}
    assert all(D(order["reserved_dollars"]) == 0 for order in orders)
    # The ledger and the exchange agree on what is held in every market.
    for index in range(FIGHTS):
        ticker = f"WIN-{index}"
        ledger = sum(D(o["filled_count"]) * (1 if o["side"] == "yes" else -1)
                     for o in orders if o["ticker"] == ticker and o["status"] == "demo_filled")
        exchange = sum(D(p["position_fp"]) for p in night.exchange.positions if p["ticker"] == ticker)
        assert ledger == exchange, f"{ticker}: ledger says {ledger}, exchange says {exchange}"
    settled_tally(night)
