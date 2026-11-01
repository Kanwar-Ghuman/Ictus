"""Automatic session setup: event, card, ESPN bouts and Kalshi markets."""

from datetime import date
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient

from octagon.trading import service
from octagon.trading.autoplan import build_plan, choose_card, quickstart_mappings, same_name
from octagon.trading.engine import TradingEngine
from octagon.trading.ledger import Ledger
from octagon.trading.service import create_app
from tests.test_trading import Exchange, card, feed, iso, request

TODAY = date.fromisoformat(iso()[:10])


def espn(bout_id, a, b, status="scheduled"):
    return {"bout_id": bout_id, "status": status, "round": None,
            "fighter_a": {"name": a}, "fighter_b": {"name": b}}


def live_feed(*bouts):
    return {"success": True, "data": list(bouts),
            "meta": {"event_id": "event-1", "event_name": "UFC Test", "event_status": "in_progress"}}


def market(event, ticker, yes, day=None):
    return {"ticker": ticker, "event_ticker": event, "yes_sub_title": yes,
            "occurrence_datetime": f"{day or TODAY.isoformat()}T23:00:00Z",
            "yes_bid_dollars": "0.4500", "yes_ask_dollars": "0.4600",
            "title": f"{yes} wins", "rules_primary": "r1", "rules_secondary": "r2"}


def detail(*bouts, slug="tonight"):
    return {"slug": slug, "event": "UFC Test", "date": TODAY.isoformat(), "bouts": [
        {"f1": a, "f2": b, "p_skill": 0.6, "scheduled_rounds": 3} for a, b in bouts]}


CARD = detail(("Renato Moicano", "Tom Nolan"), ("Ode' Osbourne", "Cody Durden"),
              ("JeongYeong Lee", "Julian Erosa"), ("Not On", "Espn Feed"))
MARKETS = [market("E1", "E1-MOI", "Renato Moicano"), market("E1", "E1-NOL", "Tom Nolan"),
           market("E2", "E2-OSB", "Ode Osbourne"), market("E2", "E2-DUR", "Cody Durden"),
           market("E3", "E3-LEE", "Jeong Yeong Lee"), market("E3", "E3-ERO", "Julian Erosa"),
           # Same names on another date must not be used.
           market("OLD", "OLD-MOI", "Renato Moicano", "2025-01-01"),
           market("OLD", "OLD-NOL", "Tom Nolan", "2025-01-01")]
FEED = live_feed(espn("1", "Tom Nolan", "Renato Moicano"),
                 espn("2", "Ode' Osbourne", "Cody Durden", "in_progress"),
                 espn("3", "Julian Erosa", "JeongYeong Lee", "final"))


def plan(in_fight=False, markets=MARKETS):
    return build_plan(FEED, [{"slug": "tonight", "date": TODAY.isoformat()}],
                      lambda slug: CARD, markets, in_fight=in_fight, today=TODAY)


def test_names_fold_accents_punctuation_and_spacing():
    assert same_name("Ode' Osbourne", "Ode Osbourne")
    assert same_name("JeongYeong Lee", "Jeong Yeong Lee")
    assert same_name("Lucia Szabová", "Lucia Szabova")
    assert not same_name("Tom Nolan", "Eric Nolan")


def test_plan_maps_every_fight_and_explains_exclusions():
    fights = {f["f1"]: f for f in plan()["fights"]}
    nolan = fights["Renato Moicano"]
    assert nolan["include"] and nolan["bout_id"] == "1"
    assert nolan["ticker"] == "E1-MOI" and nolan["yes_fighter"] == "Renato Moicano"  # YES = f1
    assert fights["Ode' Osbourne"]["note"] == "Already started" and not fights["Ode' Osbourne"]["include"]
    assert fights["JeongYeong Lee"]["note"] == "Finished"
    assert fights["Not On"]["note"] == "Not found in the ESPN feed"


def test_in_fight_mode_keeps_started_fights():
    fights = {f["f1"]: f for f in plan(in_fight=True)["fights"]}
    assert fights["Ode' Osbourne"]["include"]


def test_missing_or_ambiguous_markets_are_left_out():
    fights = {f["f1"]: f for f in plan(markets=MARKETS[2:6])["fights"]}
    assert fights["Renato Moicano"]["note"] == "No open Kalshi market found"
    twice = MARKETS + [market("E9", "E9-MOI", "Renato Moicano"), market("E9", "E9-NOL", "Tom Nolan")]
    fights = {f["f1"]: f for f in plan(markets=twice)["fights"]}
    assert fights["Renato Moicano"]["note"] == "Several Kalshi markets match"


def test_no_card_asks_for_predictions_and_old_cards_are_ignored():
    stale = {"slug": "old", "date": "2020-01-01"}
    result = build_plan(FEED, [stale], lambda slug: CARD, MARKETS, in_fight=False, today=TODAY)
    assert result["card"] is None and result["needs_predictions"]
    other = detail(("A B", "C D"), slug="other")
    best = choose_card(FEED["data"], [{"slug": "other", "date": TODAY.isoformat()},
                                      {"slug": "tonight", "date": TODAY.isoformat()}],
                       lambda slug: other if slug == "other" else CARD, TODAY)
    assert best["slug"] == "tonight"


def test_bet_fights_keep_their_original_mapping():
    previous = {"mappings": [{"bout_id": "1", "ticker": "E1-NOL", "yes_fighter": "Tom Nolan",
                              "f1": "Renato Moicano", "f2": "Tom Nolan", "confirmed": True}]}
    mappings = quickstart_mappings(plan(), previous, {"1"})
    by_bout = {m["bout_id"]: m for m in mappings}
    assert by_bout["1"]["ticker"] == "E1-NOL" and len(mappings) == 1


def test_funded_session_can_add_fights_but_not_change_bet_ones(tmp_path):
    exchange = Exchange()
    engine = TradingEngine(Ledger(tmp_path / "l.db"), exchange)
    engine.configure(request(), card())
    engine.update_feed(feed())
    engine.start()
    engine.tick()
    assert engine.ledger.orders(engine.session_id)  # fight 1 now has a bet
    engine.stop()
    engine.configure(request(two=True), card())  # adding fight 2 is fine
    changed = request(two=True)
    changed["mappings"][0]["yes_fighter"] = changed["mappings"][0]["f2"]
    with pytest.raises(ValueError):
        engine.configure(changed, card())


def test_quickstart_configures_and_starts_from_amount_only(tmp_path, monkeypatch):
    exchange = Exchange()
    names = card()["bouts"]
    exchange.list_open_markets = lambda series: [
        market("EV0", "WIN-0", names[0]["f1"]), market("EV0", "LOSE-0", names[0]["f2"])]
    engine = TradingEngine(Ledger(tmp_path / "l.db"), exchange)
    engine.update_feed(feed())
    tonight = card() | {"slug": "test_card"}
    monkeypatch.setattr(service.findings, "list_cards", lambda: [{"slug": "test_card", "date": tonight["date"]}])
    monkeypatch.setattr(service.findings, "card_detail", lambda slug: tonight)
    token = "a" * 48
    api = TestClient(create_app(engine, token))
    auth = {"Authorization": "Bearer " + token}
    proposal = api.get("/api/trading/plan", headers=auth).json()
    assert [f["include"] for f in proposal["fights"]] == [True, False]
    response = api.post("/api/trading/quickstart", json={"budget_dollars": "5.00"}, headers=auth)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["running"] and D(body["event"]["budget_dollars"]) == D("5")
    assert [m["ticker"] for m in engine.config["mappings"]] == ["WIN-0"]
    again = api.post("/api/trading/quickstart", json={"budget_dollars": "5.00"}, headers=auth)
    assert again.status_code == 400 and "Stop first" in again.json()["detail"]


def card_yaml(*pairs):
    import yaml
    return yaml.safe_dump({"date": TODAY.isoformat(), "event": "UFC Test",
                           "fights": [{"fighter1": a, "fighter2": b} for a, b in pairs]})


def preparer(tmp_path, writes):
    """CardPreparer whose CLI steps write files instead of scraping/predicting."""
    from octagon.trading.prepare import CardPreparer

    (tmp_path / "cards").mkdir(parents=True)
    (tmp_path / "reports").mkdir()
    prep = CardPreparer(tmp_path, tmp_path / "scratch")
    calls = []

    def fake(*args):
        calls.append(args)
        if args[0] == "fetch-card":
            out = args[args.index("--out") + 1]
            content = writes.get("event" if "--event" in args else "next")
            if content:
                from pathlib import Path
                Path(out).write_text(content)
        if args[0] == "predict":
            from pathlib import Path
            stem = Path(args[2]).stem
            (tmp_path / "reports" / f"card_predictions_{stem}.parquet").write_text("x")

        class Done:
            returncode = 0
        return Done()

    prep._octagon = fake
    return prep, calls


PAIRS = [("Renato Moicano", "Tom Nolan"), ("Ode' Osbourne", "Cody Durden")]


def test_prepare_fetches_named_event_then_predicts(tmp_path):
    prep, calls = preparer(tmp_path, {"event": card_yaml(*PAIRS)})
    prep._run("UFC Test", PAIRS)
    assert prep.status()["state"] == "done"
    assert [c[0] for c in calls] == ["fetch-card", "predict"]


def test_prepare_never_overwrites_an_existing_card(tmp_path):
    prep, calls = preparer(tmp_path, {"event": card_yaml(*PAIRS)})
    original = card_yaml(("Other", "Fighters"))
    (tmp_path / "cards" / "ufc_test.yaml").write_text(original)
    prep._run("UFC Test", PAIRS)
    assert prep.status()["state"] == "failed"
    assert (tmp_path / "cards" / "ufc_test.yaml").read_text() == original
    assert not calls


def test_prepare_falls_back_only_to_a_matching_next_event(tmp_path):
    prep, calls = preparer(tmp_path, {"next": card_yaml(("Unrelated", "Card"))})
    prep._run("UFC Test", PAIRS)
    assert prep.status()["state"] == "failed" and not (tmp_path / "cards" / "ufc_test.yaml").exists()
    prep, _ = preparer(tmp_path / "b", {"next": card_yaml(*PAIRS)})
    prep._run("UFC Test", PAIRS)
    assert prep.status()["state"] == "done" and (tmp_path / "b" / "cards" / "ufc_test.yaml").exists()


def test_finished_fight_reports_the_winner_by_card_name():
    final = espn("3", "Julian Erosa", "JeongYeong Lee", "final") | {"winner": "Jeong Yeong Lee"}
    result = build_plan(live_feed(final), [{"slug": "tonight", "date": TODAY.isoformat()}],
                        lambda slug: CARD, MARKETS, in_fight=False, today=TODAY)
    fight = next(f for f in result["fights"] if f["f2"] == "Julian Erosa")
    assert fight["winner"] == "JeongYeong Lee" and fight["note"] == "Finished"
