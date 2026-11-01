"""The local gateway broadcasts the live JSON array over WebSocket."""

from fastapi.testclient import TestClient

from octagon.live import espn, gateway, schema


def _snapshot():
    return espn.parse_fightcenter({
        "event": {"id": "1", "name": "Test Card"},
        "venue": {"displayNameLocation": "Apex"},
        "meta": {"gameState": "in"},
        "cards": {
            "main": {
                "competitions": [{
                    "id": "99",
                    "type": {"text": "Lightweight"},
                    "status": {
                        "displayClock": "4:00",
                        "period": 1,
                        "type": {
                            "description": "In Progress",
                            "state": "in",
                            "completed": False,
                        },
                        "result": {},
                    },
                    "cardSegment": {"description": "Main Card"},
                    "matchNumber": 1,
                    "competitors": [
                        {
                            "order": 1,
                            "winner": False,
                            "displayRecord": "1-0-0",
                            "athlete": {"displayName": "Alpha", "country": "USA"},
                            "stats": [{"name": "sigStrikes", "displayValue": "1/2"}],
                            "bets": {"odds": []},
                        },
                        {
                            "order": 2,
                            "winner": False,
                            "displayRecord": "0-1-0",
                            "athlete": {"displayName": "Bravo", "country": "USA"},
                            "stats": [{"name": "sigStrikes", "displayValue": "0/1"}],
                            "bets": {"odds": []},
                        },
                    ],
                    "officials": [],
                }]
            }
        },
    })


class _FixedCollector:
    source = "espn_fightcenter"

    def snapshot(self):
        return _snapshot()


def test_http_snapshot_returns_the_json_array_envelope():
    app = gateway.create_app(_FixedCollector(), interval=0)
    client = TestClient(app)
    body = client.get("/live").json()

    assert body["success"] is True
    assert body["error"] is None
    assert isinstance(body["data"], list)
    assert body["data"][0]["fighter_a"]["name"] == "Alpha"
    assert body["data"][0]["clock"] == "4:00"


def test_websocket_pushes_the_same_array_on_connect():
    app = gateway.create_app(_FixedCollector(), interval=0)
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        message = ws.receive_json()

    assert message["success"] is True
    assert [bout["bout_id"] for bout in message["data"]] == ["99"]
    assert message["meta"]["source"] == "espn_fightcenter"


def test_envelope_is_stable_enough_to_skip_unchanged_ticks():
    snap = _snapshot()
    first = schema.envelope(snap, source="espn_fightcenter", seq=1)
    second = schema.envelope(snap, source="espn_fightcenter", seq=2)
    assert schema.fingerprint(snap) == schema.fingerprint(snap)
    assert first["data"] == second["data"]


def test_unchanged_feed_publishes_heartbeats():
    app = gateway.create_app(_FixedCollector(), interval=0.01)
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            first = ws.receive_json()
            second = ws.receive_json()
            assert second["data"] == first["data"]
            assert second["meta"]["seq"] > first["meta"]["seq"]
            assert second["meta"]["captured_at"] >= first["meta"]["captured_at"]
