"""Immutable live-card snapshot and the JSON envelope the gateway publishes."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class FighterSnapshot:
    name: str
    record: str | None
    country: str | None
    winner: bool
    odds: str | None
    stats: dict[str, str]


@dataclass(frozen=True)
class BoutSnapshot:
    bout_id: str
    weight_class: str | None
    card_segment: str
    match_number: int | None
    status: str
    round: int | None
    clock: str | None
    method: str | None
    method_detail: str | None
    winner: str | None
    referee: str | None
    fighter_a: FighterSnapshot
    fighter_b: FighterSnapshot


@dataclass(frozen=True)
class EventSnapshot:
    event_id: str
    name: str
    venue: str | None
    status: str
    captured_at: str
    fights: tuple[BoutSnapshot, ...]


def _bout_dict(bout: BoutSnapshot) -> dict[str, Any]:
    return asdict(bout)


def fingerprint(snapshot: EventSnapshot) -> str:
    """Hash of the fight array only — clock ticks must change this."""
    payload = json.dumps(
        [_bout_dict(bout) for bout in snapshot.fights],
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha1(payload.encode()).hexdigest()


def envelope(
    snapshot: EventSnapshot,
    source: str,
    seq: int,
    error: str | None = None,
) -> dict[str, Any]:
    """Project-standard API envelope: success, data array, error, meta."""
    data = [_bout_dict(bout) for bout in snapshot.fights]
    live_ids = [bout.bout_id for bout in snapshot.fights if bout.status == "in_progress"]
    return {
        "success": error is None,
        "data": None if error else data,
        "error": error,
        "meta": {
            "event_id": snapshot.event_id,
            "event_name": snapshot.name,
            "venue": snapshot.venue,
            "event_status": snapshot.status,
            "source": source,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "espn_updated_at": snapshot.captured_at,
            "seq": seq,
            "live_bout_ids": live_ids,
            "fingerprint": fingerprint(snapshot),
        },
    }


def error_envelope(message: str, seq: int, source: str) -> dict[str, Any]:
    return {
        "success": False,
        "data": None,
        "error": message,
        "meta": {
            "source": source,
            "seq": seq,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "live_bout_ids": [],
        },
    }
