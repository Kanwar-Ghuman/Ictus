"""Automatic session setup: event, card, ESPN bouts and Kalshi markets."""

from datetime import date
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient

from octagon.trading import service
from octagon.trading.autoplan import build_plan, choose_card, quickstart_mappings
from octagon.trading.names import orient, rules_name_fight, same_name
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
    assert same_name("Waldo Cortes-Acosta", "Waldo Cortes Acosta")
    assert same_name("JeongYeong Lee", "Jeong Yeong Lee")
    assert same_name("Lucia Szabová", "Lucia Szabova")
    assert same_name("Jose Delano", "Jose Mauro Delano")
    assert same_name("Seokhyeon Ko", "Seok Hyun Ko")
    assert not same_name("Tom Nolan", "Eric Nolan")
    assert not same_name("Jon Jones", "John Jones")


def test_plan_maps_every_fight_and_explains_exclusions():
    fights = {f["f1"]: f for f in plan()["fights"]}
    nolan = fights["Renato Moicano"]
    assert nolan["include"] and nolan["bout_id"] == "1"
    assert nolan["ticker"] == "E1-MOI" and nolan["yes_fighter"] == "Renato Moicano"  # YES = f1
    assert fights["Ode' Osbourne"]["note"] == "Already started" and not fights["Ode' Osbourne"]["include"]
    assert fights["JeongYeong Lee"]["note"] == "Finished"
    assert fights["Not On"]["note"] == "Not on ESPN's card"


def test_in_fight_mode_keeps_started_fights():
    fights = {f["f1"]: f for f in plan(in_fight=True)["fights"]}
    assert fights["Ode' Osbourne"]["include"]


def test_missing_or_ambiguous_markets_are_left_out():
    fights = {f["f1"]: f for f in plan(markets=MARKETS[2:6])["fights"]}
    assert fights["Renato Moicano"]["note"] == "Kalshi has not listed this fight yet"
    twice = MARKETS + [market("E9", "E9-MOI", "Renato Moicano"), market("E9", "E9-NOL", "Tom Nolan")]
    fights = {f["f1"]: f for f in plan(markets=twice)["fights"]}
    assert fights["Renato Moicano"]["note"] == "Two Kalshi markets match this fight"


def test_no_card_asks_for_predictions_and_old_cards_are_ignored():
    stale = {"slug": "old", "date": "2020-01-01"}
    result = build_plan(FEED, [stale], lambda slug: CARD, MARKETS, in_fight=False, today=TODAY)
    assert result["card"] is None and result["needs_predictions"]
    other = detail(("A B", "C D"), slug="other")
    best = choose_card(FEED["data"], [{"slug": "other", "date": TODAY.isoformat()},
                                      {"slug": "tonight", "date": TODAY.isoformat()}],
                       lambda slug: other if slug == "other" else CARD, TODAY)
    assert best["slug"] == "tonight"


def test_next_weekends_card_is_used_but_not_one_further_out():
    from datetime import timedelta

    def chosen(days_ahead):
        day = (TODAY + timedelta(days=days_ahead)).isoformat()
        return choose_card(FEED["data"], [{"slug": "tonight", "date": day}], lambda slug: CARD, TODAY)

    assert chosen(5)["slug"] == "tonight"   # checked on Monday for Saturday
    assert chosen(-2)["slug"] == "tonight"  # a card that ran past midnight
    assert chosen(11) is None and chosen(-3) is None


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
    assert [c[0] for c in calls] == ["fetch-card", "fetch-odds", "predict"]


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


def test_the_plan_shows_the_number_the_bot_bets_and_where_its_line_came_from():
    from octagon.trading.signal import moneyline_probability, pure_stack

    feed_with_odds = live_feed(
        # ESPN lists the corners the other way round from the card.
        {**espn("1", "Tom Nolan", "Renato Moicano"),
         "fighter_a": {"name": "Tom Nolan", "odds": "+170"},
         "fighter_b": {"name": "Renato Moicano", "odds": "-205"}},
        espn("2", "Ode' Osbourne", "Cody Durden"))
    fights = build_plan(feed_with_odds, [{"slug": "tonight", "date": TODAY.isoformat()}],
                        lambda slug: CARD, MARKETS, in_fight=False, today=TODAY)["fights"]
    lined, bare = fights[0], fights[1]
    expected = pure_stack(D("0.6"), moneyline_probability("-205", "+170"))
    assert lined["line"] == "live sportsbook line" and lined["p_f1"] == pytest.approx(float(expected))
    # No line anywhere: the skill number is shown, and the source says so.
    assert bare["line"] is None and bare["p_f1"] == 0.6


def test_missing_predictions_start_themselves_once(tmp_path):
    class Preparer:
        def __init__(self):
            self.state, self.started = "idle", []

        def status(self):
            return {"state": self.state, "message": ""}

        def start(self, name, pairs):
            self.started.append(name)
            self.state = "running"
            return self.status()

    token = "a" * 48
    engine = TradingEngine(Ledger(tmp_path / "ledger.db"), Exchange())
    engine.client.list_open_markets = lambda series: []
    engine.update_feed(feed())
    preparer = Preparer()
    api = TestClient(create_app(engine, token, preparer=preparer))
    headers = {"Authorization": f"Bearer {token}"}
    # No saved card matches this feed, so the first look at the plan starts the model.
    assert api.get("/api/trading/plan", headers=headers).json()["needs_predictions"]
    assert preparer.started == ["UFC Test"]
    preparer.state = "failed"
    api.get("/api/trading/plan", headers=headers)
    assert preparer.started == ["UFC Test"]  # a failure waits for the retry button


def test_a_fight_is_matched_as_a_pair_so_a_nickname_still_matches():
    card_fight = ("Macy Chiasson", "Beatriz Mesquita")
    assert not same_name("Beatriz Mesquita", "Bia Mesquita")
    assert orient(*card_fight, "Macy Chiasson", "Bia Mesquita") is True
    assert orient(*card_fight, "Bia Mesquita", "Macy Chiasson") is False
    assert orient("Zhang Mingyang", "Volkan Oezdemir", "Volkan Oezdemir", "Mingyang Zhang") is False
    # A changed opponent is a different fight, however well one name matches.
    assert orient("Juan Diaz", "Alateng Heili", "Adrian Yañez", "Juan Diaz") is None
    assert orient("Austin Bashi", "Carlos Calderon", "Lucas Brennan", "Austin Bashi") is None
    # A nickname on both sides is not enough to go on.
    assert orient("Beatriz Mesquita", "Macarena Chiasson", "Bia Mesquita", "Macy Chiasson") is None


def test_market_rules_have_to_describe_this_fight():
    assert rules_name_fight("If Bia Mesquita beats Macy Chiasson", "Macy Chiasson", "Beatriz Mesquita")
    assert not rules_name_fight("If Ciryl Gane beats Tom Aspinall", "Ciryl Gane", "Josh Hokit")
    # A shared surname cannot stand in for the second fighter.
    assert not rules_name_fight("Alpha Fighter vs Someone Else", "Alpha Fighter", "Bravo Fighter")


def nickname_plan(feed_names, market_names, day=None):
    """The plan's view of Chiasson vs Mesquita on a card with one other, ordinary fight."""
    card_detail = detail(("Macy Chiasson", "Beatriz Mesquita"), ("Tom Nolan", "Renato Moicano"))
    markets = [market("EM", "EM-CHI", market_names[0], day), market("EM", "EM-MES", market_names[1], day)]
    live = live_feed(espn("7", *feed_names), espn("8", "Tom Nolan", "Renato Moicano"))
    return build_plan(live, [{"slug": "tonight", "date": TODAY.isoformat()}],
                      lambda slug: card_detail, markets, in_fight=False, today=TODAY)["fights"][0]


def test_the_plan_finds_the_market_when_espn_or_kalshi_use_a_nickname():
    fight = nickname_plan(("Bia Mesquita", "Macy Chiasson"), ("Macy Chiasson", "Bia Mesquita"))
    assert fight["include"] and fight["bout_id"] == "7"
    assert fight["ticker"] == "EM-CHI" and fight["yes_fighter"] == "Macy Chiasson"


def test_a_market_dated_two_days_from_the_card_is_still_tonights():
    from datetime import timedelta

    near = (TODAY + timedelta(days=2)).isoformat()
    far = (TODAY + timedelta(days=3)).isoformat()
    names = ("Macy Chiasson", "Beatriz Mesquita")
    assert nickname_plan(names, names, near)["include"]
    assert nickname_plan(names, names, far)["note"] == "Kalshi has not listed this fight yet"


def test_the_plan_says_when_the_opponent_changed():
    fight = nickname_plan(("Macy Chiasson", "Someone New"), ("Macy Chiasson", "Beatriz Mesquita"))
    assert not fight["include"]
    assert fight["note"] == ("ESPN now lists Macy Chiasson vs Someone New; "
                             "these predictions are for a different fight")
    fight = nickname_plan(("Macy Chiasson", "Beatriz Mesquita"), ("Macy Chiasson", "Someone New"))
    assert fight["note"] == "Kalshi lists Macy Chiasson vs Someone New, a different fight"


def test_one_failed_kalshi_refresh_does_not_empty_the_market_list():
    from octagon.trading.autoplan import MarketCache
    from octagon.trading.kalshi import KalshiTransportError

    class Client:
        fail = False

        def list_open_markets(self, series):
            if self.fail:
                raise KalshiTransportError("down")
            return [{"ticker": "T"}]

    client = Client()
    cache = MarketCache(client, ttl=0)
    assert cache.get() == [{"ticker": "T"}]
    client.fail = True
    cache._at = 0.0
    assert cache.get() == [{"ticker": "T"}]  # the last good list
    with pytest.raises(KalshiTransportError):
        MarketCache(client, ttl=0).get()  # nothing cached yet: say so


def test_a_fight_kalshi_lists_after_start_joins_the_running_session(tmp_path, monkeypatch):
    exchange = Exchange()
    names = card()["bouts"]
    first = [market("EV0", "WIN-0", names[0]["f1"]), market("EV0", "LOSE-0", names[0]["f2"])]
    late = [market("EV1", "WIN-1", names[1]["f1"]), market("EV1", "LOSE-1", names[1]["f2"])]
    listed = list(first)
    exchange.list_open_markets = lambda series: list(listed)
    engine = TradingEngine(Ledger(tmp_path / "l.db"), exchange)
    engine.update_feed(feed())
    tonight = card() | {"slug": "test_card"}
    monkeypatch.setattr(service.findings, "list_cards", lambda: [{"slug": "test_card", "date": tonight["date"]}])
    monkeypatch.setattr(service.findings, "card_detail", lambda slug: tonight)
    monkeypatch.setattr(service.MarketCache, "get", lambda self: self.client.list_open_markets("x"))
    token = "a" * 48
    app = create_app(engine, token)
    api = TestClient(app)
    started = api.post("/api/trading/quickstart", headers={"Authorization": f"Bearer {token}"},
                       json={"budget_dollars": "20.00"})
    assert started.status_code == 200 and started.json()["running"]
    assert [m["ticker"] for m in engine.config["mappings"]] == ["WIN-0"]
    assert app.state.add_new_fights() == []  # nothing new yet
    listed.extend(late)
    assert app.state.add_new_fights() == ["WIN-1"]
    assert engine.running.is_set()  # never stopped
    assert [m["ticker"] for m in engine.config["mappings"]] == ["WIN-0", "WIN-1"]
    assert app.state.add_new_fights() == []  # and only once
    engine.tick()
    assert {o["ticker"] for o in engine.ledger.orders(engine.session_id)} == {"WIN-0", "WIN-1"}


def test_a_fight_espn_names_differently_still_trades_and_settles(tmp_path):
    exchange = Exchange()
    engine = TradingEngine(Ledger(tmp_path / "nick.db"), exchange)
    engine.configure(request(), card())
    nicknamed = feed()
    nicknamed["data"][0]["fighter_a"]["name"] = "Al Fighter"  # ESPN's short form of Alpha Fighter
    engine.update_feed(nicknamed)
    engine.start()
    engine.tick()
    assert engine.ledger.orders(engine.session_id)
    nicknamed["data"][0].update(status="final", winner="Al Fighter")
    nicknamed["data"][0]["fighter_a"]["winner"] = True
    engine.update_feed(nicknamed)
    # Stored under the card's name, so the bet on Alpha Fighter counts as won.
    assert engine.results["1"] == {"winner": "Alpha Fighter"}
    assert engine.status()["results"]["markets"]["WIN-0"]["outcome"] == "won"


def test_the_plan_carries_the_models_own_pick_method_and_round():
    picked = detail(("Tom Nolan", "Renato Moicano"))
    picked["bouts"][0].update(
        pick="Tom Nolan", confidence=0.62, weight_class="Lightweight",
        top_outcome={"method": "KO/TKO", "round": 2, "probability": 0.11, "label": "by KO/TKO in round 2"})
    final = espn("8", "Tom Nolan", "Renato Moicano", "final") | {"method": "Submission", "round": 3}
    final["fighter_b"]["winner"] = True
    fight = build_plan(live_feed(final), [{"slug": "tonight", "date": TODAY.isoformat()}],
                       lambda slug: picked, [], in_fight=False, today=TODAY)["fights"][0]
    assert fight["pick"] == {"winner": "Tom Nolan", "confidence": 0.62, "method": "KO/TKO",
                             "round": 2, "exact_probability": 0.11}
    assert fight["weight_class"] == "Lightweight"
    assert fight["winner"] == "Renato Moicano"
    assert fight["result"] == {"method": "Submission", "round": 3}
    # A card saved without picks still plans; it just has none to show.
    assert plan()["fights"][0]["pick"] is None
