"""Propose tonight's whole session from what the service can already see.

Event from the live ESPN feed, the frozen prediction card whose fighters match
it, each card bout's ESPN bout, and its Kalshi winner market (the series event
whose two YES labels are the two fighters, near the card's date). Fights are
matched as pairs by ``names.orient``, so a nickname on one side still matches.
A fight that matches two bouts or two markets is left out and explained, never
guessed. The service validates every mapping again when the session is
configured.

Each fight also carries the probability the bot would bet (``signal``), so the
dashboard shows the same number the engine trades on.
"""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import date, datetime, timezone

from octagon.trading.engine import MARKET_DAYS
from octagon.trading.names import loose_name, orient
from octagon.trading.pnl import card_winner, corner_names
from octagon.trading.risk import decimal
from octagon.trading.signal import moneyline_probability, order_probability

SERIES = "KXUFCFIGHT"


class MarketCache:
    """Open winner markets, refreshed at most every ``ttl`` seconds."""

    def __init__(self, client, ttl: float = 30.0):
        self.client, self.ttl = client, ttl
        self._at, self._markets = 0.0, []

    def get(self) -> list[dict]:
        """The open markets. A failed refresh keeps the last list it had.

        One Kalshi hiccup must not make every market on the card disappear.
        With nothing cached yet the error is raised, so the caller can say
        Kalshi is unreachable.
        """
        if time.monotonic() - self._at > self.ttl:
            try:
                self._markets = self.client.list_open_markets(SERIES)
            except (RuntimeError, ValueError):
                if not self._markets:
                    raise
            # Wait a full interval after a failure too, not one retry per poll.
            self._at = time.monotonic()
        return self._markets


def _market_pairs(markets: list[dict]) -> list[list[dict]]:
    by_event: dict[str, list[dict]] = defaultdict(list)
    for market in markets:
        if market.get("event_ticker") and market.get("yes_sub_title"):
            by_event[market["event_ticker"]].append(market)
    return [pair for pair in by_event.values() if len(pair) == 2]


def _occurs_near(market: dict, card_date: date) -> bool:
    try:
        when = datetime.fromisoformat(str(market.get("occurrence_datetime")).replace("Z", "+00:00"))
    except ValueError:
        return False
    return abs((when.astimezone(timezone.utc).date() - card_date).days) <= MARKET_DAYS


def _other_opponent(fighters: tuple[str, str], listed: list[tuple[str, str]]) -> str | None:
    """"X vs Z" when a source lists one of these fighters against someone else."""
    for pair in listed:
        for name in fighters:
            for index in (0, 1):
                if loose_name(name, pair[index]) and not any(
                        loose_name(other, pair[1 - index]) for other in fighters if other != name):
                    return f"{pair[index]} vs {pair[1 - index]}"
    return None


# A card counts for the event ESPN is showing when it is dated from two days
# back (a late-night card past midnight) to ten days ahead (next weekend's
# card, so it can be checked during the week). Older cards with the same
# fighters are rematches, not tonight.
CARD_DAYS_BACK = 2
CARD_DAYS_AHEAD = 10


def choose_card(feed_bouts: list[dict], cards: list[dict], card_detail, today: date) -> dict | None:
    """The current card with the most bouts present in the live feed."""
    pairs = [corner_names(b) for b in feed_bouts]
    best, best_hits = None, 0
    for summary in cards:
        try:
            card_day = date.fromisoformat(str(summary["date"])[:10])
        except ValueError:
            continue
        if not -CARD_DAYS_BACK <= (card_day - today).days <= CARD_DAYS_AHEAD:
            continue
        detail = card_detail(summary["slug"])
        if not detail:
            continue
        hits = sum(any(orient(b["f1"], b["f2"], *p) is not None for p in pairs)
                   for b in detail["bouts"])
        if hits > best_hits:
            best, best_hits = detail, hits
    return best


def _bet_probability(bout: dict, espn: dict | None,
                     f1_is_a: bool | None) -> tuple[float | None, str | None]:
    """(P(f1 wins) the bot would bet, where its line came from).

    Without any line the skill number is shown so the card is still readable,
    and the source is None: the bot will not bet that fight before it starts.
    """
    skill = bout.get("p_skill")
    if not isinstance(skill, (int, float)) or not 0 < skill < 1:
        return None, None
    live = None
    if espn and f1_is_a is not None:
        odds = [(espn.get(key) or {}).get("odds") for key in ("fighter_a", "fighter_b")]
        live = moneyline_probability(*(odds if f1_is_a else reversed(odds)))
    card = bout.get("p_market")
    card = decimal(card) if isinstance(card, (int, float)) and 0 < card < 1 else None
    pick = order_probability(decimal(skill), live, card)
    return (float(pick[0]), pick[1]) if pick else (float(skill), None)


def _model_pick(bout: dict) -> dict | None:
    """The model's own call for a fight: who wins, how, and in which round.

    This is the written card's pick. It is shown beside the betting number,
    never bet: the bot trades on ``_bet_probability``.
    """
    outcome = bout.get("top_outcome")
    if not bout.get("pick") or not isinstance(outcome, dict):
        return None
    return {"winner": bout["pick"], "confidence": bout.get("confidence"),
            "method": outcome.get("method"), "round": outcome.get("round"),
            # Chance of exactly this winner, method and round together.
            "exact_probability": outcome.get("probability")}


def build_plan(feed: dict | None, cards: list[dict], card_detail, markets: list[dict],
               *, in_fight: bool, today: date | None = None) -> dict:
    today = today or date.today()
    meta = (feed or {}).get("meta") or {}
    feed_bouts = [b for b in (feed or {}).get("data") or [] if isinstance(b, dict)]
    plan = {"event": {"espn_event_id": meta.get("event_id"), "name": meta.get("event_name"),
                      "status": meta.get("event_status")},
            "card": None, "fights": [], "problem": None}
    if not feed_bouts or not meta.get("event_id"):
        plan["problem"] = "Waiting for the live fight feed. Is the fight gateway running?"
        return plan
    card = choose_card(feed_bouts, cards, card_detail, today)
    if card is None:
        plan["problem"] = "No predictions for this event yet."
        plan["needs_predictions"] = True
        return plan
    plan["card"] = {"slug": card["slug"], "event": card.get("event"), "date": card["date"]}
    card_day = date.fromisoformat(str(card["date"])[:10])
    pairs = [p for p in _market_pairs(markets) if all(_occurs_near(m, card_day) for m in p)]

    feed_pairs = [corner_names(b) for b in feed_bouts]
    market_pairs = [(p[0]["yes_sub_title"], p[1]["yes_sub_title"]) for p in pairs]

    for bout in card["bouts"]:
        f1, f2 = bout["f1"], bout["f2"]
        # (bout, is f1 ESPN's fighter_a) for every ESPN bout that is this fight.
        espn = [(b, way) for b, names in zip(feed_bouts, feed_pairs, strict=True)
                if (way := orient(f1, f2, *names)) is not None]
        live, f1_is_a = espn[0] if len(espn) == 1 else (None, None)
        p_bet, line = _bet_probability(bout, live, f1_is_a)
        fight = {"f1": f1, "f2": f2, "p_f1": p_bet, "line": line, "pick": _model_pick(bout),
                 "weight_class": bout.get("weight_class"), "result": None,
                 "scheduled_rounds": bout.get("scheduled_rounds"),
                 "bout_id": None, "status": None, "round": None, "ticker": None, "yes_fighter": None,
                 "yes_bid": None, "yes_ask": None, "title": None, "rules_primary": None,
                 "rules_secondary": None, "include": False, "note": "", "winner": None}
        if live:
            fight.update(bout_id=str(live.get("bout_id")), status=live.get("status"),
                         round=live.get("round"), winner=card_winner(live, f1, f2, f1_is_a))
            if live.get("status") == "final":
                # How it actually ended, in ESPN's words, to set beside the pick.
                fight["result"] = {"method": live.get("method"), "round": live.get("round")}
        # (the two markets, is f1 the first market's YES fighter)
        matched = [(p, way) for p, names in zip(pairs, market_pairs, strict=True)
                   if (way := orient(f1, f2, *names)) is not None]
        if len(matched) == 1:
            (first, second), f1_is_first = matched[0]
            market = first if f1_is_first else second  # the market whose YES is f1
            fight.update(ticker=market["ticker"], yes_fighter=f1,
                         yes_bid=market.get("yes_bid_dollars"), yes_ask=market.get("yes_ask_dollars"),
                         title=market.get("title"), rules_primary=market.get("rules_primary"),
                         rules_secondary=market.get("rules_secondary"))
        if len(espn) != 1:
            changed = _other_opponent((f1, f2), feed_pairs)
            fight["note"] = ("Two ESPN bouts match this fight" if espn
                             else f"ESPN now lists {changed}; these predictions are for a different fight"
                             if changed else "Not on ESPN's card")
        elif fight["status"] in {"final", "unavailable", "unknown"}:
            fight["note"] = "Finished" if fight["status"] == "final" else "Unavailable"
        elif len(matched) != 1:
            changed = _other_opponent((f1, f2), market_pairs)
            fight["note"] = ("Two Kalshi markets match this fight" if matched
                             else f"Kalshi lists {changed}, a different fight" if changed
                             else "Kalshi has not listed this fight yet")
        elif p_bet is None:
            fight["note"] = "No model prediction"
        elif fight["status"] == "in_progress" and not in_fight:
            fight["note"] = "Already started"
        else:
            fight["include"] = True
        plan["fights"].append(fight)
    if not any(f["include"] for f in plan["fights"]):
        plan["problem"] = "No fights on this card can be traded right now."
    return plan


def quickstart_mappings(plan: dict, previous: dict | None, attempted: set[str]) -> list[dict]:
    """Auto mappings plus, unchanged, every earlier mapping that already has a bet."""
    kept = [{k: old[k] for k in ("bout_id", "ticker", "yes_fighter", "f1", "f2")} | {"confirmed": True}
            for old in (previous or {}).get("mappings", []) if old["bout_id"] in attempted]
    locked = {m["bout_id"] for m in kept}
    return kept + [{"bout_id": f["bout_id"], "ticker": f["ticker"], "yes_fighter": f["yes_fighter"],
                    "f1": f["f1"], "f2": f["f2"], "confirmed": True}
                   for f in plan["fights"] if f["include"] and f["bout_id"] not in locked]
