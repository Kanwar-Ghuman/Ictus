"""Propose tonight's whole session from what the service can already see.

Event from the live ESPN feed, the frozen prediction card whose fighters match
it, each card bout's ESPN bout, and its Kalshi winner market (the series event
whose two YES labels are exactly the two fighters, on the card's date). Names
must match exactly after accent/punctuation folding: anything ambiguous is
left out and explained, never guessed. The service still validates every
mapping again when the session is configured.
"""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import date, datetime, timezone

from octagon.trading.engine import normalized_name

SERIES = "KXUFCFIGHT"


def _skeleton(name: str) -> str:
    return "".join(c for c in name if c not in "aeiouy ")


def same_name(a: str, b: str) -> bool:
    x, y = normalized_name(a), normalized_name(b)
    if not x or not y:
        return False
    if x == y or x.replace(" ", "") == y.replace(" ", ""):
        return True
    xt, yt = x.split(), y.split()
    if not xt or not yt or xt[-1] != yt[-1]:
        return False
    shorter, longer = (xt, yt) if len(xt) <= len(yt) else (yt, xt)
    if len(shorter) >= 2 and set(shorter) <= set(longer):
        return True
    sx, sy = _skeleton(x), _skeleton(y)
    return len(sx) >= 4 and sx == sy


def fighter_in_rules(fighter: str, rules: str) -> bool:
    folded = normalized_name(fighter)
    text = normalized_name(rules)
    if not folded or not text:
        return False
    if f" {folded} " in f" {text} ":
        return True
    tokens = folded.split()
    words = text.split()
    if len(tokens) < 2 or tokens[-1] not in words:
        return False
    if all(token in words for token in tokens):
        return True
    skeleton = _skeleton(folded)
    return len(skeleton) >= 4 and skeleton in _skeleton(text)


def same_pair(pair: tuple[str, str], other: tuple[str, str]) -> bool:
    return ((same_name(pair[0], other[0]) and same_name(pair[1], other[1]))
            or (same_name(pair[0], other[1]) and same_name(pair[1], other[0])))


class MarketCache:
    """Open winner markets, refreshed at most every ``ttl`` seconds."""

    def __init__(self, client, ttl: float = 30.0):
        self.client, self.ttl = client, ttl
        self._at, self._markets = 0.0, []

    def get(self) -> list[dict]:
        if time.monotonic() - self._at > self.ttl:
            self._markets = self.client.list_open_markets(SERIES)
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
    return abs((when.astimezone(timezone.utc).date() - card_date).days) <= 1


def choose_card(feed_bouts: list[dict], cards: list[dict], card_detail, today: date) -> dict | None:
    """The recent card with the most bouts present in the live feed."""
    pairs = [((b.get("fighter_a") or {}).get("name", ""), (b.get("fighter_b") or {}).get("name", ""))
             for b in feed_bouts]
    best, best_hits = None, 0
    for summary in cards:
        try:
            card_day = date.fromisoformat(str(summary["date"])[:10])
        except ValueError:
            continue
        if abs((card_day - today).days) > 2:
            continue
        detail = card_detail(summary["slug"])
        if not detail:
            continue
        hits = sum(any(same_pair((b["f1"], b["f2"]), p) for p in pairs) for b in detail["bouts"])
        if hits > best_hits:
            best, best_hits = detail, hits
    return best


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

    for bout in card["bouts"]:
        f1, f2 = bout["f1"], bout["f2"]
        p_pick = bout.get("p_f1_wins")
        if not isinstance(p_pick, (int, float)):
            p_pick = bout.get("p_skill")
        fight = {"f1": f1, "f2": f2, "p_f1": p_pick, "scheduled_rounds": bout.get("scheduled_rounds"),
                 "bout_id": None, "status": None, "round": None, "ticker": None, "yes_fighter": None,
                 "yes_bid": None, "yes_ask": None, "title": None, "rules_primary": None,
                 "rules_secondary": None, "include": False, "note": "", "winner": None}
        espn = [b for b in feed_bouts if same_pair(
            (f1, f2), ((b.get("fighter_a") or {}).get("name", ""), (b.get("fighter_b") or {}).get("name", "")))]
        if len(espn) == 1:
            winner = espn[0].get("winner")
            fight.update(bout_id=str(espn[0].get("bout_id")), status=espn[0].get("status"),
                         round=espn[0].get("round"),
                         winner=next((n for n in (f1, f2) if winner and same_name(n, winner)), None))
        matched = [p for p in pairs if same_pair((f1, f2), (p[0]["yes_sub_title"], p[1]["yes_sub_title"]))]
        if len(matched) == 1:
            market = next((m for m in matched[0] if same_name(m["yes_sub_title"], f1)), matched[0][0])
            fight.update(ticker=market["ticker"],
                         yes_fighter=f1 if same_name(market["yes_sub_title"], f1) else f2,
                         yes_bid=market.get("yes_bid_dollars"), yes_ask=market.get("yes_ask_dollars"),
                         title=market.get("title"), rules_primary=market.get("rules_primary"),
                         rules_secondary=market.get("rules_secondary"))
        if len(espn) != 1:
            fight["note"] = "Not found in the ESPN feed"
        elif fight["status"] in {"final", "unavailable", "unknown"}:
            fight["note"] = "Finished" if fight["status"] == "final" else "Unavailable"
        elif len(matched) != 1:
            fight["note"] = "No open Kalshi market found" if not matched else "Several Kalshi markets match"
        elif not isinstance(p_pick, (int, float)) or not 0 < p_pick < 1:
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
