"""Between-rounds model and in-fight execution; exchange activity is faked."""

import sqlite3
from decimal import Decimal as D

import pytest

from octagon.inplay import live as live_mod
from octagon.inplay.live import BREAK_STATUS, break_inputs, parse_stats
from octagon.inplay.model import FEATURES, InplayModel
from octagon.live.espn import _parse_bout
from octagon.trading.engine import TradingEngine, normalized_name
from octagon.trading.ledger import Ledger
from tests.test_trading import Exchange, card, feed, iso, request

ESPN_STATS = {"knockDowns": "0", "totalStrikes": "20/40", "sigStrikes": "15/30",
              "headStrikes": "8/20", "bodyStrikes": "4/5", "legStrikes": "3/5",
              "timeInControl": "1:34", "takedowns": "1/2", "submissions": "0"}
QUIET = {**ESPN_STATS, "totalStrikes": "5/20", "sigStrikes": "3/15", "headStrikes": "1/10",
         "bodyStrikes": "1/3", "legStrikes": "1/2", "timeInControl": "0:00", "takedowns": "0/1"}


def toy_model(sig_weight=0.2):
    coef = dict.fromkeys(FEATURES, 0.0)
    coef["prior"], coef["sig_l"] = 1.0, sig_weight
    return InplayModel(scale=dict.fromkeys(FEATURES, 1.0), coef=coef, meta={})


def stats(**overrides):
    out = {"sig_l": 10, "sig_a": 20, "head_l": 5, "body_l": 3, "leg_l": 2, "tot_l": 12,
           "td_l": 1, "td_a": 2, "kd": 0, "sub": 0, "ctrl": 60}
    return out | overrides


def test_corner_swap_is_exact_complement():
    coef = {name: 0.1 * (i + 1) * (-1) ** i for i, name in enumerate(FEATURES)}
    model = InplayModel(scale=dict.fromkeys(FEATURES, 1.0), coef=coef, meta={})
    a, b = stats(sig_l=30, kd=1), stats(ctrl=200)
    for k, scheduled in ((1, 3), (2, 3), (4, 5)):
        p = model.predict_one(a, b, 0.62, k, scheduled)
        q = model.predict_one(b, a, 0.38, k, scheduled)
        assert p + q == pytest.approx(1.0, abs=1e-12)


def test_rejects_inputs_outside_trained_range():
    model = toy_model()
    with pytest.raises(ValueError):
        model.predict_one(stats(), stats(), 0.5, 3, 3)  # no break after the final round
    with pytest.raises(ValueError):
        model.predict_one(stats(), stats(), 0.5, 1, 4)
    with pytest.raises(ValueError):
        model.predict_one(stats(), stats(), 1.0, 1, 3)


def test_artifact_round_trip(tmp_path):
    model = toy_model()
    model.save(tmp_path / "inplay.json")
    loaded = InplayModel.load(tmp_path / "inplay.json")
    assert loaded.predict_one(stats(sig_l=20), stats(), 0.5, 1, 3) == pytest.approx(
        model.predict_one(stats(sig_l=20), stats(), 0.5, 1, 3))


def test_espn_live_stats_parse_to_training_units():
    parsed = parse_stats(ESPN_STATS)
    assert parsed["sig_l"] == 15 and parsed["sig_a"] == 30 and parsed["ctrl"] == 94
    assert parsed["td_l"] == 1 and parsed["head_l"] == 8 and parsed["tot_l"] == 20
    for bad in ({**ESPN_STATS, "sigStrikes": "9/8"}, {**ESPN_STATS, "timeInControl": "1:75"},
                {k: v for k, v in ESPN_STATS.items() if k != "knockDowns"}):
        with pytest.raises(ValueError):
            parse_stats(bad)


def test_break_inputs_only_during_a_break_and_by_name():
    bout = {"status": "in_progress", "status_detail": BREAK_STATUS, "round": 1,
            "fighter_a": {"name": "Bravo Fighter", "stats": QUIET},
            "fighter_b": {"name": "Alpha Fighter", "stats": ESPN_STATS}}
    k, s1, s2 = break_inputs(bout, "Alpha Fighter", "Bravo Fighter", normalized_name)
    assert k == 1 and s1["sig_l"] == 15 and s2["sig_l"] == 3  # oriented by name, not slot
    for change in ({"status_detail": "STATUS_IN_PROGRESS_2"}, {"round": None},
                   {"status": "final"}):
        with pytest.raises(ValueError):
            break_inputs(bout | change, "Alpha Fighter", "Bravo Fighter", normalized_name)
    with pytest.raises(ValueError):
        break_inputs(bout, "Alpha Fighter", "Someone Else", normalized_name)


def test_espn_parser_keeps_raw_status_name():
    bout = _parse_bout({"id": "9", "status": {"period": 1, "displayClock": "-", "type": {
        "name": "STATUS_END_OF_ROUND", "state": "in"}}, "competitors": []})
    assert bout.status == "in_progress" and bout.status_detail == BREAK_STATUS


def inplay_card():
    c = card()
    for bout in c["bouts"]:
        bout["scheduled_rounds"] = 3
        bout["p_skill"] = 0.5  # no pre-fight edge: isolate the in-fight path
        bout["p_market"] = None
    return c


def break_feed(round_k=1, detail=BREAK_STATUS, a_stats=ESPN_STATS, b_stats=QUIET):
    message = feed()
    bout = message["data"][0]
    bout.update(status="in_progress", status_detail=detail, round=round_k)
    bout["fighter_a"]["stats"], bout["fighter_b"]["stats"] = a_stats, b_stats
    message["meta"]["captured_at"] = message["meta"]["espn_updated_at"] = iso()
    return message


def in_fight_engine(tmp_path, model=None):
    exchange = Exchange()
    engine = TradingEngine(Ledger(tmp_path / "ledger.db"), exchange, inplay=model or toy_model(),
                           prefight_path=tmp_path / "prefight.json")
    engine.configure(request(), inplay_card())
    return engine, exchange


def settle_break(engine, bout_id="1", round_k=1):
    engine.break_seen[(bout_id, round_k)] -= engine.policy.min_break_seconds + 1


def test_prefight_price_is_captured_while_scheduled_and_persisted(tmp_path):
    engine, _ = in_fight_engine(tmp_path)
    engine.update_feed(feed())
    engine.start()
    engine.tick()
    assert D(engine.prefight["WIN-0"]["p_f1"]) == D("0.495")  # (0.50 ask + 0.49 bid) / 2
    reloaded = TradingEngine(engine.ledger, Exchange(), inplay=toy_model(),
                             prefight_path=tmp_path / "prefight.json")
    assert D(reloaded.prefight["WIN-0"]["p_f1"]) == D("0.495")


def test_in_fight_trades_in_break_only_after_totals_settle_with_bounded_retries(tmp_path):
    engine, _ = in_fight_engine(tmp_path)
    engine.update_feed(feed())
    engine.start()
    engine.tick()  # captures the pre-fight price
    engine.update_feed(break_feed(1))
    assert not engine.ledger.blocked(engine.session_id, "1")  # in progress is not terminal
    engine.tick()
    assert "settle" in engine.decisions[0]["reason"] and not engine.ledger.orders(engine.session_id)
    settle_break(engine)
    engine.tick()
    decision = engine.decisions[0]
    assert decision["action"] == "paper" and decision["phase"] == "after round 1"
    assert decision["prior"] == "initial pick"
    orders = engine.ledger.orders(engine.session_id)
    assert [o["bout_id"] for o in orders] == ["1:r1"]
    engine.tick()
    assert "Waiting" in engine.decisions[0]["reason"]
    assert len(engine.ledger.orders(engine.session_id)) == 1
    for _ in range(engine.policy.max_break_attempts + 2):
        engine.last_attempt.clear()
        engine.tick()
    keys = [o["bout_id"] for o in engine.ledger.orders(engine.session_id)]
    assert len(keys) <= engine.policy.max_break_attempts
    assert all(k == "1:r1" or k.startswith("1:r1:") for k in keys)


def test_late_in_the_break_is_refused(tmp_path):
    engine, _ = in_fight_engine(tmp_path)
    engine.update_feed(feed())
    engine.start()
    engine.tick()
    engine.update_feed(break_feed(1))
    engine.break_seen[("1", 1)] -= engine.policy.max_break_seconds + 1
    engine.tick()
    assert "Too late" in engine.decisions[0]["reason"]
    assert not engine.ledger.orders(engine.session_id)


def test_live_action_without_a_clock_or_after_the_final_round_does_not_trade(tmp_path):
    engine, _ = in_fight_engine(tmp_path)
    engine.update_feed(feed())
    engine.start()
    engine.tick()
    engine.update_feed(break_feed(1, detail="STATUS_IN_PROGRESS_2"))
    engine.tick()
    assert "clock" in engine.decisions[0]["reason"].lower()
    engine.update_feed(break_feed(3))
    settle_break(engine, round_k=3)
    engine.tick()
    assert "Final round" in engine.decisions[0]["reason"]
    assert not engine.ledger.orders(engine.session_id)


def test_each_break_shares_one_bout_cap(tmp_path):
    engine, _ = in_fight_engine(tmp_path, toy_model(sig_weight=1.0))
    engine.update_feed(feed())
    engine.start()
    engine.tick()
    for round_k in (1, 2):
        engine.update_feed(break_feed(round_k))
        settle_break(engine, round_k=round_k)
        engine.tick()
    orders = engine.ledger.orders(engine.session_id)
    spent = sum(D(o["cost_dollars"]) + D(o["reserved_dollars"]) for o in orders)
    budget = D(request()["budget_dollars"])
    assert spent <= budget * engine.policy.max_bout_fraction
    assert orders and {o["bout_id"] for o in orders} <= {"1:r1", "1:r2"}


def test_finished_bout_is_blocked_and_skill_prior_needs_history(tmp_path):
    engine, _ = in_fight_engine(tmp_path)
    engine.start()
    engine.update_feed(break_feed(1))  # no pre-fight Kalshi price was ever captured
    settle_break(engine)
    engine.tick()
    assert engine.decisions[0].get("prior") == "initial pick"
    final = break_feed(1)
    final["data"][0].update(status="final", status_detail="STATUS_FINAL")
    engine.update_feed(final)
    engine.tick()
    assert engine.ledger.blocked(engine.session_id, "1")


def test_default_engine_still_blocks_started_bouts(tmp_path):
    engine = TradingEngine(Ledger(tmp_path / "ledger.db"), Exchange())
    engine.configure(request(), inplay_card())
    engine.update_feed(break_feed(1))
    engine.start()
    engine.tick()
    assert engine.ledger.blocked(engine.session_id, "1")
    assert not engine.ledger.orders(engine.session_id)


def test_old_journal_migrates_to_per_attempt_uniqueness(tmp_path):
    path = tmp_path / "old.db"
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE sessions (id TEXT PRIMARY KEY, event_id TEXT NOT NULL, mode TEXT NOT NULL,
            card_slug TEXT NOT NULL, budget INTEGER NOT NULL CHECK(budget > 0), config TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(event_id, mode));
        CREATE TABLE orders (id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
            bout_id TEXT NOT NULL, ticker TEXT NOT NULL, side TEXT NOT NULL, count INTEGER NOT NULL,
            price TEXT NOT NULL, reserved INTEGER NOT NULL, spent INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL, exchange_order_id TEXT, filled_count TEXT NOT NULL DEFAULT '0',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(session_id, bout_id), UNIQUE(session_id, ticker));
        INSERT INTO sessions(id,event_id,mode,card_slug,budget,config) VALUES('s','e','live','c',5000000,'{}');
        INSERT INTO orders(id,session_id,bout_id,ticker,side,count,price,reserved,spent,status,filled_count)
            VALUES('o','s','1','T','yes',2,'0.46',0,954800,'filled','2.00');
    """)
    db.commit()
    db.close()
    ledger = Ledger(path)
    rows = ledger.orders("s")
    assert len(rows) == 1 and rows[0]["cost_dollars"] == "0.9548"
    with ledger.connection() as db:
        db.execute("INSERT INTO orders(id,session_id,bout_id,ticker,side,count,price,reserved,status) "
                   "VALUES('o2','s','1:r1','T','yes',1,'0.5',0,'paper_filled')")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO orders(id,session_id,bout_id,ticker,side,count,price,reserved,status) "
                       "VALUES('o3','s','1:r1','T','yes',1,'0.5',0,'paper_filled')")
    Ledger(path)  # idempotent


def test_cli_in_fight_flag_loads_artifact(monkeypatch, tmp_path):
    from octagon.trading import __main__ as cli

    calls = []
    monkeypatch.setattr(cli, "run", lambda *a, **k: calls.append(k))
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    cli.main(["--mode", "paper"])
    cli.main(["--mode", "paper", "--in-fight", "--inplay-artifact", str(tmp_path / "m.json")])
    assert calls[0]["inplay_artifact"] is None
    assert calls[1]["inplay_artifact"] == tmp_path / "m.json"


def test_monotonic_in_strike_lead():
    model = toy_model()
    base = model.predict_one(stats(), stats(), 0.5, 1, 3)
    ahead = model.predict_one(stats(sig_l=25), stats(), 0.5, 1, 3)
    assert ahead > base


def progress_model():
    coef = dict.fromkeys(FEATURES, 0.0)
    coef["sig_l_x_frac"] = 1.0
    return InplayModel(scale=dict.fromkeys(FEATURES, 1.0), coef=coef, meta={})


def test_live_progress_rises_as_the_clock_runs_and_swaps_corners():
    model = progress_model()
    ahead, behind = stats(sig_l=30), stats(sig_l=10)
    early = model.predict_progress(ahead, behind, 0.5, 0.5, 3)
    late = model.predict_progress(ahead, behind, 0.5, 2.5, 3)
    swapped = model.predict_progress(behind, ahead, 0.5, 2.5, 3)
    assert late > early
    assert early + model.predict_progress(behind, ahead, 0.5, 0.5, 3) == pytest.approx(1.0, abs=1e-12)
    assert late + swapped == pytest.approx(1.0, abs=1e-12)
    for elapsed, scheduled in ((0, 3), (3, 3), (1.5, 4), (float("nan"), 3)):
        with pytest.raises(ValueError):
            model.predict_progress(ahead, behind, 0.5, elapsed, scheduled)


def live_feed(clock="2:30", round_k=1, detail="STATUS_IN_PROGRESS"):
    message = break_feed(round_k, detail=detail)
    message["data"][0]["clock"] = clock
    return message


def test_fight_progress_uses_the_round_clock_and_completed_breaks():
    bout = live_feed(clock="2:30", round_k=2)["data"][0]
    elapsed, s1, s2, phase = live_mod.fight_progress(
        bout, "Alpha Fighter", "Bravo Fighter", normalized_name)
    assert phase == "live" and elapsed == pytest.approx(1.5)
    assert s1["sig_l"] == 15 and s2["sig_l"] == 3
    breaking = break_feed(1)["data"][0]
    elapsed, _, _, phase = live_mod.fight_progress(
        breaking, "Alpha Fighter", "Bravo Fighter", normalized_name)
    assert phase == "break" and elapsed == 1
    for change in ({"clock": None}, {"clock": "-"}, {"clock": "6:00"}, {"status": "final"}):
        with pytest.raises(ValueError):
            live_mod.fight_progress(bout | change, "Alpha Fighter", "Bravo Fighter", normalized_name)


def one_contract(exchange):
    exchange.get_orderbook = lambda ticker: {"orderbook_fp": {
        "yes_dollars": [["0.4900", "1.00"]], "no_dollars": [["0.5000", "1.00"]]}}


def live_price_model():
    """Same strike lead is cheap early and expensive only once the clock is late."""
    coef = dict.fromkeys(FEATURES, 0.0)
    coef["sig_l_x_frac"] = 0.15
    return InplayModel(scale=dict.fromkeys(FEATURES, 1.0), coef=coef, meta={})


def test_live_clock_can_change_the_price_and_trade(tmp_path):
    engine, exchange = in_fight_engine(tmp_path, live_price_model())
    one_contract(exchange)
    engine.update_feed(feed())
    engine.start()
    engine.tick()
    engine.update_feed(live_feed(clock="4:30", round_k=1))
    engine.tick()
    early = engine.decisions[0]
    assert early["action"] == "skip" and "No edge" in early["reason"]
    assert early["phase"] == "live round 1"
    engine.update_feed(live_feed(clock="0:30", round_k=3))
    engine.tick()
    late = engine.decisions[0]
    assert late["action"] == "paper" and late["phase"] == "live round 3"
    assert late["p_f1"] != early["p_f1"]


def test_control_without_a_finish_is_not_a_buy(tmp_path):
    assert live_mod.held_without_threat(stats(ctrl=6, kd=0, sub=1), stats(ctrl=9 * 60 + 12))
    assert not live_mod.held_without_threat(stats(ctrl=9 * 60 + 12), stats(ctrl=6, kd=0, sub=1))
    assert not live_mod.held_without_threat(stats(ctrl=6, kd=1), stats(ctrl=9 * 60 + 12))
    engine, exchange = in_fight_engine(tmp_path, toy_model())
    priced = inplay_card()
    priced["bouts"][0]["p_skill"] = 0.70
    engine.configure(request(), priced)
    exchange.get_orderbook = lambda ticker: {"orderbook_fp": {
        "yes_dollars": [["0.0500", "100.00"]], "no_dollars": [["0.9400", "100.00"]]}}
    buried = {**QUIET, "timeInControl": "0:06", "submissions": "1", "knockDowns": "0"}
    top = {**ESPN_STATS, "timeInControl": "9:12", "submissions": "0", "knockDowns": "0"}
    message = break_feed(3, detail="STATUS_IN_PROGRESS", a_stats=buried, b_stats=top)
    message["data"][0]["clock"] = "2:00"
    engine.update_feed(feed())
    engine.start()
    engine.update_feed(message)
    engine.tick()
    assert engine.ledger.orders(engine.session_id) == []
    assert "being controlled" in engine.decisions[0]["reason"]
    assert "Alpha Fighter" in engine.decisions[0]["reason"]


def test_in_fight_checks_run_on_the_live_retry_cadence(tmp_path):
    import inspect

    from octagon.trading.service import decide

    engine, _ = in_fight_engine(tmp_path)
    assert engine.decision_interval == engine.policy.live_retry_seconds == 1.0
    plain = TradingEngine(engine.ledger, Exchange())
    assert plain.decision_interval == 2.0
    assert "decision_interval" in inspect.getsource(decide)
