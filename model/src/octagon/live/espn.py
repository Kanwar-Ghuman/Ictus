"""Turn ESPN's public fightcenter / scoreboard JSON into EventSnapshot.

These endpoints are undocumented and keyless. They power espn.com/mma/fightcenter
in the browser; we read the same JSON the page already fetches. No paid API.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from octagon.live.schema import BoutSnapshot, EventSnapshot, FighterSnapshot

STATUS_BY_STATE = {
    "pre": "scheduled",
    "in": "in_progress",
    "post": "final",
}


def discover_event_id(scoreboard: dict[str, Any]) -> str | None:
    """Prefer an in-progress UFC event, otherwise the first one on the board."""
    events = scoreboard.get("events") or []
    if not events:
        return None
    for event in events:
        state = ((event.get("status") or {}).get("type") or {}).get("state")
        if state == "in":
            return str(event["id"])
    return str(events[0]["id"])


def parse_fightcenter(payload: dict[str, Any]) -> EventSnapshot:
    event = payload.get("event") or {}
    venue = payload.get("venue") or {}
    meta = payload.get("meta") or {}
    fights: list[BoutSnapshot] = []
    cards = payload.get("cards") or {}
    for card in cards.values():
        for raw in card.get("competitions") or []:
            fights.append(_parse_bout(raw))
    captured = meta.get("lastUpdatedAt") or datetime.now(timezone.utc).isoformat()
    return EventSnapshot(
        event_id=str(event.get("id") or ""),
        name=str(event.get("name") or ""),
        venue=venue.get("displayNameLocation") or venue.get("fullName"),
        status=_event_status(meta.get("gameState"), fights),
        captured_at=str(captured),
        fights=tuple(fights),
    )


def _event_status(game_state: str | None, fights: list[BoutSnapshot]) -> str:
    if game_state in STATUS_BY_STATE:
        return STATUS_BY_STATE[game_state]
    if any(bout.status == "in_progress" for bout in fights):
        return "in_progress"
    if fights and all(bout.status == "final" for bout in fights):
        return "final"
    return "scheduled"


def _parse_bout(raw: dict[str, Any]) -> BoutSnapshot:
    status_block = raw.get("status") or {}
    status_type = status_block.get("type") or {}
    result = status_block.get("result") or {}
    competitors = sorted(
        raw.get("competitors") or [],
        key=lambda row: int(row.get("order") or 99),
    )
    fighters = [_parse_fighter(row) for row in competitors]
    if len(fighters) < 2:
        empty = FighterSnapshot("", None, None, False, None, {})
        fighters = (fighters + [empty, empty])[:2]
    winner = next((fighter.name for fighter in fighters if fighter.winner), None)
    return BoutSnapshot(
        bout_id=str(raw.get("id") or ""),
        weight_class=_weight_class(raw),
        card_segment=((raw.get("cardSegment") or {}).get("description") or "Card"),
        match_number=_maybe_int(raw.get("matchNumber")),
        status=STATUS_BY_STATE.get(status_type.get("state"), "scheduled"),
        round=_maybe_int(status_block.get("period")),
        clock=_clock(status_block.get("displayClock")),
        method=_text(result.get("displayName")),
        method_detail=_text(result.get("displayDescription") or result.get("description")),
        winner=winner,
        referee=_referee(raw.get("officials") or []),
        fighter_a=fighters[0],
        fighter_b=fighters[1],
    )


def _parse_fighter(raw: dict[str, Any]) -> FighterSnapshot:
    athlete = raw.get("athlete") or {}
    return FighterSnapshot(
        name=str(athlete.get("displayName") or athlete.get("fullName") or ""),
        record=raw.get("displayRecord"),
        country=athlete.get("country") or ((athlete.get("flag") or {}).get("alt")),
        winner=bool(raw.get("winner")),
        odds=_moneyline(raw.get("bets") or {}),
        stats=_stats(raw.get("stats") or []),
    )


def _stats(rows: list[dict[str, Any]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in rows:
        name = row.get("name")
        value = row.get("displayValue")
        if name and value is not None:
            out[str(name)] = str(value)
    return out


def _moneyline(bets: dict[str, Any]) -> str | None:
    for odd in bets.get("odds") or []:
        if odd.get("type") == "moneyline":
            values = odd.get("values") or []
            if values:
                return values[0].get("odds")
    return None


def _weight_class(raw: dict[str, Any]) -> str | None:
    text = (raw.get("type") or {}).get("text") or raw.get("note")
    return str(text) if text else None


def _referee(officials: list[dict[str, Any]]) -> str | None:
    for official in officials:
        position = ((official.get("position") or {}).get("name") or "").lower()
        if position == "referee":
            first = official.get("firstName") or ""
            last = official.get("lastName") or ""
            name = f"{first} {last}".strip()
            return name or None
    return None


def _clock(value: Any) -> str | None:
    if value in (None, "", "-"):
        return None
    return str(value)


def _text(value: Any) -> str | None:
    if not value:
        return None
    return str(value)


def _maybe_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number else None
