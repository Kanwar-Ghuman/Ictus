"""Normalize ESPN fightcenter / scoreboard payloads into the live JSON array.

These fixtures were captured from UFC Fight Night: Moicano vs. Nolan while
Marshall vs Hope was in progress. The parser has to keep the live clock,
in-fight stats, and finish method — that is the whole point of the gateway.
"""

import json
from pathlib import Path

from octagon.live import espn, schema

FIXTURE = Path(__file__).parent / "fixtures" / "live" / "fightcenter_slim.json"

SCOREBOARD = {
    "events": [
        {
            "id": "600061420",
            "name": "UFC Fight Night: Moicano vs. Nolan",
            "date": "2026-10-31T21:00Z",
            "status": {
                "type": {
                    "id": "2",
                    "name": "STATUS_IN_PROGRESS",
                    "state": "in",
                    "completed": False,
                    "description": "In Progress",
                }
            },
            "competitions": [{"id": "401931615"}],
        }
    ]
}


def _payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_fightcenter_becomes_a_json_array_of_bouts():
    snapshot = espn.parse_fightcenter(_payload())
    envelope = schema.envelope(snapshot, source="espn_fightcenter", seq=1)

    assert envelope["success"] is True
    assert envelope["error"] is None
    assert isinstance(envelope["data"], list)
    assert len(envelope["data"]) == 4
    assert envelope["meta"]["event_id"] == "600061420"
    assert envelope["meta"]["event_name"] == "UFC Fight Night: Moicano vs. Nolan"
    assert envelope["meta"]["venue"] == "Meta APEX, Las Vegas, NV"
    assert envelope["meta"]["live_bout_ids"] == ["401931615"]


def test_live_bout_keeps_round_clock_and_strike_counts():
    snapshot = espn.parse_fightcenter(_payload())
    live = next(b for b in snapshot.fights if b.bout_id == "401931615")

    assert live.status == "in_progress"
    assert live.round == 1
    assert live.clock == "3:51"
    assert live.weight_class == "Featherweight"
    assert live.card_segment == "Prelims"
    assert live.fighter_a.name == "Francis Marshall"
    assert live.fighter_b.name == "Dakota Hope"
    assert live.fighter_b.stats["sigStrikes"] == "3/8"
    assert live.method is None


def test_finished_bouts_keep_method_and_winner():
    snapshot = espn.parse_fightcenter(_payload())
    by_id = {b.bout_id: b for b in snapshot.fights}

    ko = by_id["401928109"]
    assert ko.status == "final"
    assert ko.winner == "Julian Erosa"
    assert ko.method == "KO/TKO"
    assert ko.method_detail == "Punch"
    assert ko.round == 1
    assert ko.clock == "1:31"

    sub = by_id["401914106"]
    assert sub.winner == "Joe Kropschot"
    assert sub.method == "Submission"
    assert sub.method_detail == "Triangle Choke With Armbar"
    assert sub.round == 2


def test_scheduled_main_event_stays_unfinished():
    snapshot = espn.parse_fightcenter(_payload())
    main = next(b for b in snapshot.fights if b.bout_id == "401921310")

    assert main.status == "scheduled"
    assert main.fighter_a.name == "Renato Moicano"
    assert main.fighter_b.name == "Tom Nolan"
    assert main.winner is None
    assert main.card_segment == "Main Card"


def test_scoreboard_discovers_the_in_progress_event_id():
    event_id = espn.discover_event_id(SCOREBOARD)
    assert event_id == "600061420"


def test_dash_clock_is_treated_as_missing():
    """ESPN sends '-' between rounds; that is not a live time."""
    payload = _payload()
    live = payload["cards"]["prelims1"]["competitions"][0]
    live["status"]["displayClock"] = "-"
    snapshot = espn.parse_fightcenter(payload)
    bout = next(b for b in snapshot.fights if b.bout_id == "401931615")
    assert bout.clock is None


def test_fingerprint_changes_when_the_live_clock_ticks():
    payload = _payload()
    first = espn.parse_fightcenter(payload)
    live = payload["cards"]["prelims1"]["competitions"][0]
    live["status"]["displayClock"] = "3:49"
    live["status"]["type"]["detail"] = "R1, 3:49"
    second = espn.parse_fightcenter(payload)

    assert schema.fingerprint(first) != schema.fingerprint(second)


def test_missing_source_time_does_not_become_receipt_time():
    payload = _payload()
    payload["meta"].pop("lastUpdatedAt", None)
    snapshot = espn.parse_fightcenter(payload)
    result = schema.envelope(snapshot, source="espn_fightcenter", seq=1)
    assert result["meta"]["espn_updated_at"] is None
    assert result["meta"]["captured_at"]


def test_unknown_or_postponed_bout_is_never_scheduled():
    payload = _payload()
    raw = payload["cards"]["prelims1"]["competitions"][0]
    raw["status"]["type"] = {"state": "mystery"}
    parsed = espn.parse_fightcenter(payload)
    assert next(b for b in parsed.fights if b.bout_id == raw["id"]).status == "unknown"
    raw["status"]["type"] = {"state": "pre", "name": "STATUS_POSTPONED"}
    parsed = espn.parse_fightcenter(payload)
    assert next(b for b in parsed.fights if b.bout_id == raw["id"]).status == "unavailable"
