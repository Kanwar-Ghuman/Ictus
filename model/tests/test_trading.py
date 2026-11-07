"""Deterministic execution safety tests; all exchange activity uses a fake client."""

import copy
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient

from octagon.trading.engine import TradingEngine, rest_quotes
from octagon.trading.kalshi import KalshiTransportError
from octagon.trading.ledger import Ledger
from octagon.trading.risk import RiskPolicy, bout_allowance, money, size_candidate
from octagon.trading.service import Recorder, create_app, local_gateway, process_lease


def iso(seconds=0):
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def card():
    return {"slug": "test_card", "event": "UFC Test", "date": iso()[:10], "bouts": [
        {"f1": "Alpha Fighter", "f2": "Bravo Fighter", "p_skill": 0.8, "p_market": 0.8,
         "f1_ufc_fights": 8, "f2_ufc_fights": 8},
        {"f1": "Charlie Fighter", "f2": "Delta Fighter", "p_skill": 0.8, "p_market": 0.8,
         "f1_ufc_fights": 8, "f2_ufc_fights": 8},
    ]}


def request(two=False):
    mappings = []
    for index, bout in enumerate(card()["bouts"][:2 if two else 1]):
        mappings.append({"bout_id": str(index + 1), "ticker": f"WIN-{index}",
                         "f1": bout["f1"], "f2": bout["f2"],
                         "yes_fighter": bout["f1"], "confirmed": True})
    return {"card_slug": "test_card", "espn_event_id": "event-1",
            "budget_dollars": "200.00", "mappings": mappings}


def feed():
    return {"success": True, "data": [
        {"bout_id": str(i + 1), "status": "scheduled", "round": None,
         "winner": None, "method": None,
         "fighter_a": {"name": b["f1"], "winner": False},
         "fighter_b": {"name": b["f2"], "winner": False}}
        for i, b in enumerate(card()["bouts"])
    ], "meta": {"event_id": "event-1", "event_name": "UFC Test", "event_status": "in_progress",
                "captured_at": iso(), "espn_updated_at": iso(), "seq": 1}}


class Exchange:
    environment = "demo"

    def __init__(self):
        self.orders = {}
        self.fills = {}
        self.sent = []
        self.raise_on_submit = None
        self.hide_orders = False
        self.positions = []
        self.status = "active"
        self.fee_type = "quadratic"
        self.partial_count = None

    def get_market(self, ticker):
        index = int(ticker.split("-")[-1])
        return {"ticker": ticker, "market_type": "binary", "yes_sub_title": card()["bouts"][index]["f1"],
                "event_ticker": "KXUFCFIGHT-EVENT", "rules_primary": (
                    f'Winner of {card()["bouts"][index]["f1"]} vs {card()["bouts"][index]["f2"]}.'
                ), "occurrence_datetime": iso(3600),
                "status": self.status, "open_time": iso(-3600), "close_time": iso(3600),
                "notional_value_dollars": "1.0000", "exchange_index": 0}

    def get_event(self, ticker):
        return {"series_ticker": "KXUFCFIGHT"}

    def get_series(self, ticker):
        return {"fee_type": self.fee_type, "fee_multiplier": 1}

    def get_exchange_status(self):
        return {"trading_active": True}

    def get_orderbook(self, ticker):
        return {"orderbook_fp": {"yes_dollars": [["0.4900", "100.00"]],
                                 "no_dollars": [["0.5000", "100.00"]]}}

    def get_balance(self):
        return {"balance": 100000}

    def list_orders(self, **kwargs):
        return []

    def list_positions(self, **kwargs):
        return self.positions

    def create_ioc_order(self, ticker, side, price, count, client_order_id):
        self.sent.append(client_order_id)
        if self.raise_on_submit:
            raise self.raise_on_submit
        quantity = self.partial_count if self.partial_count is not None else D(count)
        self.orders[client_order_id] = {
            "order_id": client_order_id, "client_order_id": client_order_id,
            "ticker": ticker, "outcome_side": side, "book_side": "bid" if side == "yes" else "ask",
            "status": "executed" if quantity == count else "canceled",
            "fill_count_fp": str(quantity), "remaining_count_fp": "0.00",
            "initial_count_fp": str(count),
        }
        self.fills[client_order_id] = [] if quantity == 0 else [{
            "fill_id": "fill-" + client_order_id, "order_id": client_order_id, "ticker": ticker,
            "outcome_side": side, "book_side": "bid" if side == "yes" else "ask",
            "count_fp": str(quantity), "yes_price_dollars": str(price if side == "yes" else 1 - price),
            "fee_cost": "0.01",
        }]
        self.positions.append({"ticker": ticker, "position_fp": str(quantity if side == "yes" else -quantity)})
        return {"order_id": client_order_id, "client_order_id": client_order_id}

    def get_order(self, order_id):
        return self.orders[order_id]

    def find_order_by_client_id(self, client_id, **kwargs):
        return None if self.hide_orders else self.orders.get(client_id)

    def list_fills(self, order_id):
        return self.fills[order_id]


@pytest.fixture
def setup(tmp_path):
    exchange = Exchange()
    engine = TradingEngine(Ledger(tmp_path / "ledger.db"), exchange)
    engine.configure(request(), card())
    engine.update_feed(feed())
    return engine, exchange


def candidate(**overrides):
    args = dict(side="yes", probability=D("0.8"), price=D("0.5"), depth=D(100),
                spread=D("0.01"), allowance=D(10), fee_multiplier=D(1), policy=RiskPolicy())
    args.update(overrides)
    return size_candidate(**args)


@pytest.mark.parametrize("amount", ["nan", "Infinity", "-1", "1.001", True, "invalid"])
def test_budget_is_finite_exact_nonnegative(amount):
    with pytest.raises(ValueError):
        money(amount)


def test_sizing_never_forces_spend_or_exceeds_displayed_depth():
    assert candidate(probability=D("0.54")) is None
    assert candidate(allowance=D("0.01")) is None
    assert candidate(spread=D("0.2")) is None
    assert candidate(depth=D("0.99")) is None
    result = candidate(depth=D("3.9"))
    assert result.count == 3
    assert result.estimated_cost <= result.reserved_cost <= D("10")


def test_paper_fills_once_and_never_calls_exchange_order(setup):
    engine, exchange = setup
    engine.start()
    engine.tick()
    engine.update_feed(feed())
    engine.tick()
    status = engine.status()
    assert not exchange.sent
    assert len(status["orders"]) == 1
    assert status["orders"][0]["status"] == "paper_filled"
    # One fight, huge edge: capped at 40% of the $200 budget and by displayed depth.
    assert D(status["event"]["spent_dollars"]) <= D("80")
    assert D(status["event"]["reserved_dollars"]) == 0
    assert status["readiness"]["live_enabled"] is False


@pytest.mark.parametrize("change", [
    lambda f: f["meta"].update(espn_updated_at=None),
    lambda f: f["meta"].update(espn_updated_at=iso(-100)),
    lambda f: f["meta"].update(captured_at=iso(-100)),
    lambda f: f["meta"].update(espn_updated_at=iso(100)),
    lambda f: f["meta"].update(event_id="wrong"),
    lambda f: f["meta"].update(event_status="final"),
    lambda f: f.update(success=False, data=None),
    lambda f: f["data"][0].update(status="in_progress"),
    lambda f: f["data"][0].update(status="final"),
    lambda f: f["data"][0].update(status="unknown"),
    lambda f: f["data"][0].update(round=1),
    lambda f: f["data"][0]["fighter_a"].update(name="Someone Else"),
    lambda f: f["data"].append(copy.deepcopy(f["data"][0])),
])
def test_ineligible_feed_never_spends(setup, change):
    engine, exchange = setup
    message = feed()
    change(message)
    engine.update_feed(message)
    engine.start()
    engine.tick()
    assert engine.status()["orders"] == []
    assert engine.status()["decisions"][0]["action"] == "skip"


def test_started_bout_cannot_be_reopened_by_later_scheduled_packet(setup):
    engine, _ = setup
    message = feed()
    message["data"][0]["status"] = "in_progress"
    engine.update_feed(message)
    engine.update_feed(feed())
    engine.start()
    engine.tick()
    assert not engine.status()["orders"]
    recovered = TradingEngine(engine.ledger, Exchange())
    recovered.update_feed(feed())
    recovered.start()
    recovered.tick()
    assert not recovered.status()["orders"]


def test_disconnection_and_stop_during_quote_block_dispatch(setup):
    engine, exchange = setup
    original = exchange.get_orderbook

    def slow_quote(ticker):
        engine.stop()
        return original(ticker)

    exchange.get_orderbook = slow_quote
    engine.start()
    engine.tick()
    assert not engine.status()["orders"]
    engine.disconnect_feed()
    assert engine.status()["feed_connected"] is False


@pytest.mark.parametrize("field,value", [("status", "closed"), ("fee_type", "flat")])
def test_unavailable_market_or_unknown_fees_block(setup, field, value):
    engine, exchange = setup
    setattr(exchange, field, value)
    engine.start()
    engine.tick()
    assert not engine.status()["orders"]


def demo_engine(tmp_path, exchange=None):
    exchange = exchange or Exchange()
    engine = TradingEngine(Ledger(tmp_path / "demo.db"), exchange, mode="demo")
    engine.sleep = lambda seconds: None
    engine.configure(request(), card())
    engine.update_feed(feed())
    return engine, exchange


def test_fractional_demo_fill_releases_only_verified_unused_reservation(tmp_path):
    exchange = Exchange()
    exchange.partial_count = D("2.50")
    engine, _ = demo_engine(tmp_path, exchange)
    engine.start()
    engine.tick()
    order = engine.status()["orders"][0]
    assert order["filled_count"] == "2.50"
    assert D(order["cost_dollars"]) == D("1.26")
    assert order["status"] == "demo_filled"
    engine.stop()
    engine.start()  # Own reconciled positions are allowed after a restart.


def test_settled_prior_bout_does_not_block_remaining_bout(tmp_path):
    engine, exchange = demo_engine(tmp_path)
    engine.configure(request(two=True), card())
    first_feed = feed()
    first_feed["data"] = first_feed["data"][:1]
    engine.update_feed(first_feed)
    engine.start()
    engine.tick()
    engine.stop()
    assert len(exchange.sent) == 1
    exchange.positions = []  # First bout has settled at the exchange.
    engine.update_feed(feed())
    engine.start()
    engine.tick()
    assert len(exchange.sent) == 2


def test_slow_start_cannot_override_later_stop(tmp_path):
    engine, exchange = demo_engine(tmp_path)
    entered, released = threading.Event(), threading.Event()

    def slow_balance():
        entered.set()
        assert released.wait(3)
        return {"balance": 100000}

    exchange.get_balance = slow_balance
    with ThreadPoolExecutor(max_workers=1) as pool:
        started = pool.submit(engine.start)
        assert entered.wait(3)
        assert engine.stop()["running"] is False
        released.set()
        with pytest.raises(ValueError, match="canceled by Stop"):
            started.result(timeout=3)
    assert not engine.running.is_set()


def test_start_requires_reviewed_configuration_and_current_process(setup):
    engine, exchange = setup
    auth = {"Authorization": "Bearer " + "a" * 48}
    api = TestClient(create_app(engine, "a" * 48))
    old = engine.status()
    reviewed = {"session_id": old["event"]["session_id"], "config_version": old["config_version"]}
    assert api.post("/api/trading/start", headers=auth, json={}).status_code == 422
    changed = request()
    changed["budget_dollars"] = "500.00"
    engine.configure(changed, card())
    assert api.post("/api/trading/start", headers=auth, json=reviewed).status_code == 400
    assert not engine.running.is_set()
    recovered = TradingEngine(engine.ledger, exchange)
    assert recovered.config_version() != engine.config_version()
    with pytest.raises(ValueError, match="changed"):
        recovered.start(session_id=engine.session_id, config_version=engine.config_version())


def test_stop_invalidates_start_requests_that_arrive_late(setup):
    engine, _ = setup
    auth = {"Authorization": "Bearer " + "a" * 48}
    api = TestClient(create_app(engine, "a" * 48))
    start_body = {"session_id": engine.session_id, "config_version": engine.config_version()}
    assert api.post("/api/trading/stop", headers=auth, json={}).status_code == 200
    assert api.post("/api/trading/start", headers=auth, json=start_body).status_code == 400
    assert not engine.running.is_set()


def test_wrong_opponent_or_wrong_market_date_is_not_eligible(setup):
    engine, exchange = setup
    original = exchange.get_market

    def other_opponent(ticker):
        return original(ticker) | {"rules_primary": "Alpha Fighter vs Someone Else"}

    exchange.get_market = other_opponent
    with pytest.raises(ValueError, match="both exact fighters"):
        engine.configure(request(), card())

    def old_event(ticker):
        return original(ticker) | {"occurrence_datetime": iso(-10 * 86400)}

    exchange.get_market = old_event
    engine.start()
    engine.tick()
    assert not engine.status()["orders"]
    assert "occurrence date" in engine.status()["decisions"][0]["reason"]


def test_unknown_manual_demo_position_blocks_unattempted_market(tmp_path):
    engine, exchange = demo_engine(tmp_path)
    exchange.positions = [{"ticker": "WIN-0", "position_fp": "1.00"}]
    with pytest.raises(ValueError, match="holdings differ"):
        engine.start()


def test_no_purchase_uses_no_liability_and_preserves_direction(tmp_path):
    engine, exchange = demo_engine(tmp_path)
    changed = card()
    changed["bouts"][0]["p_skill"] = 0.2
    changed["bouts"][0]["p_market"] = 0.2
    engine.configure(request(), changed)
    engine.start()
    engine.tick()
    order = engine.status()["orders"][0]
    assert order["side"] == "no"
    assert order["status"] == "demo_filled"
    assert D(order["cost_dollars"]) == D(order["count"]) * D("0.51") + D("0.01")
    assert exchange.fills[order["id"]][0]["yes_price_dollars"] == "0.4900"


def test_timeout_keeps_reservation_across_restart_and_never_retries(tmp_path):
    engine, exchange = demo_engine(tmp_path)
    exchange.raise_on_submit = KalshiTransportError("timeout", ambiguous=True)
    engine.start()
    engine.tick()
    assert not engine.running.is_set()
    assert D(engine.status()["event"]["reserved_dollars"]) > 0
    engine.reconcile()
    assert D(engine.status()["event"]["reserved_dollars"]) > 0
    recovered = TradingEngine(engine.ledger, exchange, mode="demo")
    with pytest.raises(ValueError, match="Unresolved"):
        recovered.start()
    recovered.tick()
    assert len(exchange.sent) == 1


def test_definitive_rejection_releases_but_read_error_after_ack_does_not(tmp_path):
    engine, exchange = demo_engine(tmp_path)
    exchange.raise_on_submit = KalshiTransportError("forbidden", status_code=403, ambiguous=False)
    engine.start()
    engine.tick()
    assert engine.status()["orders"][0]["status"] == "rejected"
    assert D(engine.status()["event"]["reserved_dollars"]) == 0
    engine2, exchange2 = demo_engine(tmp_path / "second")

    def failed_read(order_id):
        raise KalshiTransportError("read failed", status_code=403, ambiguous=False)

    exchange2.get_order = failed_read
    engine2.start()
    engine2.tick()
    assert engine2.status()["orders"][0]["status"] == "unknown"
    assert D(engine2.status()["event"]["reserved_dollars"]) > 0


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "wrong_side", "over_limit"])
def test_incomplete_or_invalid_fills_never_release_reservation(tmp_path, mutation):
    engine, exchange = demo_engine(tmp_path)
    original = exchange.list_fills

    def changed(order_id):
        rows = copy.deepcopy(original(order_id))
        if mutation == "missing":
            return []
        if mutation == "duplicate":
            return rows + rows
        if mutation == "wrong_side":
            rows[0]["outcome_side"] = "no"
        if mutation == "over_limit":
            rows[0]["fee_cost"] = "100000.00"
        return rows

    exchange.list_fills = changed
    engine.start()
    engine.tick()
    assert D(engine.status()["event"]["reserved_dollars"]) > 0
    assert not engine.running.is_set()


def test_journal_prevents_budget_reset_and_recovers_last_selected_event(setup):
    engine, _ = setup
    engine.start()
    engine.tick()
    engine.stop()
    smaller = request()
    smaller["budget_dollars"] = "0.01"
    with pytest.raises(ValueError, match="below spent"):
        engine.configure(smaller, card())
    other = request()
    other["espn_event_id"] = "event-2"
    engine.configure(other, card())
    engine.configure(request(), card())
    recovered = TradingEngine(engine.ledger, Exchange())
    assert recovered.status()["event"]["event_id"] == "event-1"
    assert D(recovered.status()["event"]["spent_dollars"]) > 0
    assert recovered.running.is_set() is False


def test_unfunded_card_switch_updates_persisted_slug(setup):
    engine, _ = setup
    changed_card, changed_request = card(), request()
    changed_card["slug"] = changed_request["card_slug"] = "updated_card"
    engine.configure(changed_request, changed_card)
    assert engine.status()["event"]["card_slug"] == "updated_card"


def test_concurrent_ledger_reservations_cannot_double_spend(setup):
    engine, _ = setup

    def reserve(i):
        try:
            return engine.ledger.reserve(engine.session_id, str(i), f"T-{i}", candidate())
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(reserve, range(8)))
    assert sum(result is not None for result in results) == 1
    assert D(engine.status()["event"]["reserved_dollars"]) <= D(200)


def test_service_requires_auth_and_rejects_other_origins(setup):
    engine, _ = setup
    token = "a" * 48
    api = TestClient(create_app(engine, token))
    assert api.get("/api/trading/status").status_code == 401
    auth = {"Authorization": "Bearer " + token}
    assert api.get("/api/trading/status", headers=auth).status_code == 200
    assert api.post("/api/trading/start", headers=auth | {"Origin": "https://evil.example"}).status_code == 403
    response = api.post("/api/trading/configure", json=request() | {"mode": "live"}, headers=auth)
    assert response.status_code == 422
    assert api.get("/api/trading/status", headers=auth | {"Host": "evil.example"}).status_code == 400


@pytest.mark.parametrize("url", ["ws://example.com/ws", "http://127.0.0.1/ws",
                                 "ws://127.0.0.1/ws?token=secret", "ws://user@localhost/ws"])
def test_gateway_is_loopback_only(url):
    with pytest.raises(ValueError):
        local_gateway(url)


def test_live_mode_requires_live_enabled_production_client_and_cap(tmp_path):
    ledger = Ledger(tmp_path / "ledger.db")
    with pytest.raises(ValueError, match="live-enabled production client"):
        TradingEngine(ledger, Exchange(), mode="live", max_budget=D("5"))
    exchange = Exchange()
    exchange.environment = "production"
    with pytest.raises(ValueError, match="live-enabled production client"):
        TradingEngine(ledger, exchange, mode="live", max_budget=D("5"))
    exchange.live_enabled = True
    with pytest.raises(ValueError, match="hard maximum event budget"):
        TradingEngine(ledger, exchange, mode="live")
    with pytest.raises(ValueError, match="Mode must be"):
        TradingEngine(ledger, exchange, mode="production", max_budget=D("5"))


def test_live_mode_enforces_hard_cap_and_submits_through_exchange(tmp_path):
    exchange = Exchange()
    exchange.environment, exchange.live_enabled = "production", True
    loose = RiskPolicy(max_bout_fraction=D("1"))
    engine = TradingEngine(Ledger(tmp_path / "live.db"), exchange, mode="live", max_budget=D("5"),
                           policy=loose)
    engine.sleep = lambda seconds: None
    over = request()
    over["budget_dollars"] = "5.01"
    with pytest.raises(ValueError, match="hard cap"):
        engine.configure(over, card())
    capped = request()
    capped["budget_dollars"] = "5.00"
    engine.configure(capped, card())
    engine.update_feed(feed())
    engine.start()
    engine.tick()
    status = engine.status()
    assert status["readiness"]["live_enabled"] is True
    assert status["max_budget_dollars"] == "5"
    assert exchange.sent
    assert status["decisions"][-1]["action"] == "live"
    assert status["orders"][0]["status"] == "filled" and engine.running.is_set()
    assert D(status["event"]["spent_dollars"]) + D(status["event"]["reserved_dollars"]) <= D("5")


def test_cli_live_mode_requires_confirmation_and_cap(monkeypatch):
    from octagon.trading import __main__ as cli

    calls = []
    monkeypatch.setattr(cli, "run", lambda *a, **k: calls.append((a, k)))
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    with pytest.raises(SystemExit):
        cli.main(["--mode", "live", "--max-event-dollars", "5"])
    with pytest.raises(SystemExit):
        cli.main(["--mode", "live", "--confirm-real-money"])
    with pytest.raises(SystemExit):
        cli.main(["--mode", "live", "--confirm-real-money", "--max-event-dollars", "5",
                  "--max-bout-fraction", "1.5"])
    assert not calls
    cli.main(["--mode", "live", "--confirm-real-money", "--max-event-dollars", "5",
              "--max-bout-fraction", "1", "--min-edge", "0.02", "--inplay-reserve", "0.5",
              "--min-ufc-fights", "0", "--max-source-age-seconds", "180"])
    (args, kwargs), = calls
    assert args[0] == "live" and args[4] == "production"
    assert kwargs["max_event_dollars"] == D("5")
    policy = kwargs["policy"]
    assert policy.max_bout_fraction == D("1") and policy.min_net_edge == D("0.02")
    assert policy.inplay_reserve == D("0.5") and policy.min_ufc_fights == 0
    assert kwargs["policy"].max_source_age_seconds == 180


def test_process_lease_and_record_rotation(tmp_path):
    with process_lease(tmp_path):
        with pytest.raises(ValueError, match="already owns"):
            with process_lease(tmp_path):
                pass
    record = Recorder(tmp_path, max_bytes=100)
    for i in range(10):
        record("test", {"index": i})
    assert len(list(tmp_path.glob("observations.jsonl*"))) <= 4


def test_rest_book_does_not_accept_cents_or_nan_as_dollars():
    with pytest.raises(ValueError):
        rest_quotes({"orderbook": {"yes": [[49, 100]], "no": [[50, 100]]}})
    with pytest.raises(ValueError):
        rest_quotes({"orderbook_fp": {"yes_dollars": [["NaN", "1"]],
                                     "no_dollars": [["0.5", "1"]]}})


def test_lagging_fill_records_are_rechecked_without_pausing(tmp_path):
    exchange = Exchange()
    engine, _ = demo_engine(tmp_path, exchange)
    real_fills, calls = exchange.list_fills, []

    def lagging(order_id):
        calls.append(order_id)
        return [] if len(calls) == 1 else real_fills(order_id)

    exchange.list_fills = lagging
    engine.start()
    engine.tick()
    assert len(calls) == 2 and len(exchange.sent) == 1
    assert engine.running.is_set()
    order = engine.status()["orders"][0]
    assert order["status"] == "demo_filled" and D(engine.status()["event"]["reserved_dollars"]) == 0


def test_quiet_but_connected_market_stream_is_not_stale(setup):
    engine, exchange = setup
    engine.market_stream_required = True
    engine.update_book({"type": "orderbook_snapshot", "sid": 1, "seq": 1, "msg": {
        "market_ticker": "WIN-0", "yes_dollars_fp": [["0.4900", "100.00"]],
        "no_dollars_fp": [["0.5000", "100.00"]]}})
    assert engine.book.last_updated("WIN-0") is not None
    with engine.book_lock:
        engine.book._books["WIN-0"].received_at -= 60  # no deltas for a minute
    engine.start()
    engine.tick()
    assert engine.status()["market_connected"] is True
    assert all("websocket" not in d["reason"] for d in engine.status()["decisions"])
    engine.disconnect_book()
    assert engine.status()["market_connected"] is False


def test_oct31_brown_smith_edge_now_trades():
    # Model 38% vs a 29¢ ask: ~7¢ edge after fees. The old 5pt haircut + 4pt bar skipped it.
    result = candidate(probability=D("0.3795"), price=D("0.29"), allowance=D("1.00"))
    assert result is not None and result.count == 3
    assert result.net_edge >= RiskPolicy().min_net_edge


def test_budget_is_split_across_open_fights_by_conviction():
    policy = RiskPolicy()
    common = dict(budget=D(12), remaining=D(12), phase_available=D(12), phase_pool=D(12),
                  open_bouts=12, phase_bout_spent=D(0), bout_spent=D(0), policy=policy)
    assert bout_allowance(kelly=D("0.10"), **common) == D(1)       # one slice
    assert bout_allowance(kelly=D("0.05"), **common) == D("0.5")   # weak edge, half a slice
    assert bout_allowance(kelly=D("0.90"), **common) == D(2)       # capped at two slices
    # Later in the night, unused money flows to the fights that are left.
    late = common | dict(phase_pool=D(12), open_bouts=2)
    assert bout_allowance(kelly=D("0.05"), **late) == D(3)
    assert bout_allowance(kelly=D("0.90"), **late) == D("4.8")     # 40% per-fight ceiling
    assert bout_allowance(kelly=D("0.05"), **late | dict(phase_bout_spent=D(3))) == 0


def test_small_budget_long_card_still_buys_one_contract():
    # Oct 31 numbers: $5 budget, in-fight reserve, 12 fights -> 29¢ slice < 31¢ contract.
    policy = RiskPolicy()
    room = dict(budget=D(5), remaining=D(5), phase_available=D("3.5"), phase_pool=D("3.5"),
                open_bouts=12, phase_bout_spent=D(0), bout_spent=D(0), policy=policy)
    allowance = bout_allowance(kelly=D("0.10"), unit_cost=D("0.31"), **room)
    assert allowance == D("0.31")
    assert candidate(probability=D("0.3795"), price=D("0.29"), allowance=allowance).count == 1
    # ...but only once per fight per phase, and never past the hard limits.
    assert bout_allowance(kelly=D("0.10"), unit_cost=D("0.31"),
                          **room | dict(phase_bout_spent=D("0.31"))) == 0
    assert bout_allowance(kelly=D("0.10"), unit_cost=D("0.31"),
                          **room | dict(phase_available=D("0.20"))) == D("0.20")


def test_budget_is_shared_across_the_card_not_first_come(tmp_path):
    exchange = Exchange()
    engine = TradingEngine(Ledger(tmp_path / "card.db"), exchange)
    engine.configure(request(two=True), card())
    engine.update_feed(feed())
    engine.start()
    engine.tick()
    orders = engine.status()["orders"]
    assert {o["bout_id"] for o in orders} == {"1", "2"}
    # Two strong edges each get up to two half-budget slices, capped at 40% each.
    assert all(D(o["cost_dollars"]) <= D("80") for o in orders)


def test_missed_order_is_retried_after_cooldown(tmp_path):
    exchange = Exchange()
    exchange.environment, exchange.live_enabled = "production", True
    engine = TradingEngine(Ledger(tmp_path / "retry.db"), exchange, mode="live",
                           max_budget=D("200"))
    engine.sleep = lambda seconds: None
    engine.configure(request(), card())
    engine.update_feed(feed())
    engine.start()
    exchange.partial_count = D(0)          # IOC misses: price moved away
    engine.tick()
    assert engine.status()["orders"][0]["status"] == "unfilled"
    engine.update_feed(feed())
    engine.tick()                          # inside the cooldown: no new attempt
    assert len(engine.status()["orders"]) == 1
    assert "Waiting" in engine.status()["decisions"][0]["reason"]
    engine.last_attempt["1"] -= RiskPolicy().prefight_retry_seconds
    exchange.partial_count = None
    engine.update_feed(feed())
    engine.tick()
    orders = engine.status()["orders"]
    assert [o["bout_id"] for o in orders] == ["1:p2", "1"]
    assert orders[0]["status"] == "filled"
    assert len(exchange.sent) == 2


def test_retries_are_bounded(setup):
    engine, _ = setup
    policy = engine.policy
    engine.start()
    for _ in range(policy.max_prefight_attempts + 2):
        engine.last_attempt.clear()
        engine.update_feed(feed())
        engine.tick()
    assert len(engine.status()["orders"]) <= policy.max_prefight_attempts


def test_debut_fighter_blocked_but_one_fight_allowed(tmp_path):
    engine = TradingEngine(Ledger(tmp_path / "h.db"), Exchange())
    debut, one = card(), card()
    debut["bouts"][0]["f1_ufc_fights"] = 0
    one["bouts"][0]["f1_ufc_fights"] = 1
    engine.configure(request(), debut)
    engine.update_feed(feed())
    engine.start()
    engine.tick()
    assert "history" in engine.status()["decisions"][0]["reason"]
    engine.stop()
    engine.configure(request(), one)
    engine.start()
    engine.update_feed(feed())
    engine.tick()
    assert engine.status()["orders"]


def test_pre_fight_abstains_without_a_vig_free_line(tmp_path):
    engine = TradingEngine(Ledger(tmp_path / "line.db"), Exchange())
    bare = card()
    bare["bouts"][0]["p_market"] = None
    engine.configure(request(), bare)
    engine.update_feed(feed())
    engine.start()
    engine.tick()
    assert not engine.status()["orders"]
    assert "vig-free" in engine.status()["decisions"][0]["reason"]


def test_pre_fight_orders_the_pure_stack_not_raw_skill(tmp_path):
    from octagon.trading.signal import pure_stack

    engine = TradingEngine(Ledger(tmp_path / "stack.db"), Exchange())
    priced = card()
    priced["bouts"][0]["p_skill"] = 0.8
    priced["bouts"][0]["p_market"] = 0.6
    engine.configure(request(), priced)
    stored = D(engine.config["mappings"][0]["probability_f1"])
    assert stored == pure_stack(D("0.8"), D("0.6"))
    assert stored != D("0.8")
    assert engine.config["mappings"][0]["probability_layer"] == "pure_stack"
    engine.update_feed(feed())
    engine.start()
    engine.tick()
    decision = engine.status()["decisions"][0]
    assert decision["action"] == "paper"
    assert decision["layer"] == "pure_stack"
    assert D(str(decision["p_f1"])) == stored


def test_draw_rate_shrinks_a_favorite_and_helps_a_dog():
    from octagon.trading.risk import edge_of

    favorite = RiskPolicy(draw_settlement_rate=D("0.04"))
    plain = RiskPolicy()
    _, favored, _ = edge_of(D("0.70"), D("0.60"), D(1), favorite)
    _, unadjusted, _ = edge_of(D("0.70"), D("0.60"), D(1), plain)
    _, dog, _ = edge_of(D("0.30"), D("0.20"), D(1), favorite)
    _, dog_plain, _ = edge_of(D("0.30"), D("0.20"), D(1), plain)
    assert favored < unadjusted
    assert dog > dog_plain


def test_venue_lag_refuses_a_kalshi_ask_the_sportsbook_does_not_beat(tmp_path):
    engine = TradingEngine(Ledger(tmp_path / "lag.db"), Exchange(),
                           policy=RiskPolicy(venue_lag=True))
    priced = card()
    # Book, stack, and the 50¢ ask all sit together. Skill is not allowed to invent a lag.
    priced["bouts"][0]["p_skill"] = 0.52
    priced["bouts"][0]["p_market"] = 0.52
    priced["bouts"][0]["p_book"] = 0.52
    engine.configure(request(), priced)
    engine.update_feed(feed())
    engine.start()
    engine.tick()
    assert not engine.status()["orders"]
    assert "not lagging" in engine.status()["decisions"][0]["reason"]
    slow = card()
    slow["bouts"][0]["p_skill"] = 0.8
    slow["bouts"][0]["p_market"] = 0.8
    slow["bouts"][0]["p_book"] = 0.8
    engine.stop()
    engine.configure(request(), slow)
    engine.update_feed(feed())
    engine.start()
    engine.tick()
    assert engine.status()["orders"]
