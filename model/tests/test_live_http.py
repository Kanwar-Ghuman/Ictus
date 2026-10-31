"""HTTP collector talks to the public ESPN fightcenter URLs, nothing paid."""

from octagon.live.http import FIGHTCENTER_URL, SCOREBOARD_URL, HttpCollector


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []
        self.headers = {}

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        return _FakeResponse(self.routes[url])


def test_collector_discovers_tonight_then_reads_fightcenter():
    fightcenter = FIGHTCENTER_URL.format(event_id="600061420")
    session = _FakeSession({
        SCOREBOARD_URL: {
            "events": [{
                "id": "600061420",
                "name": "UFC Fight Night: Moicano vs. Nolan",
                "status": {"type": {"state": "in"}},
            }]
        },
        fightcenter: {
            "event": {"id": "600061420", "name": "UFC Fight Night: Moicano vs. Nolan"},
            "venue": {"displayNameLocation": "Meta APEX, Las Vegas, NV"},
            "meta": {"gameState": "in", "lastUpdatedAt": "2026-10-31T23:42:08Z"},
            "cards": {
                "main": {
                    "competitions": [{
                        "id": "99",
                        "type": {"text": "Lightweight"},
                        "status": {
                            "displayClock": "4:10",
                            "period": 2,
                            "type": {"state": "in", "description": "In Progress"},
                            "result": {},
                        },
                        "cardSegment": {"description": "Main Card"},
                        "matchNumber": 1,
                        "competitors": [
                            {
                                "order": 1,
                                "winner": False,
                                "athlete": {"displayName": "Alpha"},
                                "stats": [],
                                "bets": {"odds": []},
                            },
                            {
                                "order": 2,
                                "winner": False,
                                "athlete": {"displayName": "Bravo"},
                                "stats": [],
                                "bets": {"odds": []},
                            },
                        ],
                    }]
                }
            },
        },
    })
    collector = HttpCollector(session=session)
    snapshot = collector.snapshot()

    assert snapshot.event_id == "600061420"
    assert snapshot.fights[0].clock == "4:10"
    assert [url for url, _ in session.calls] == [SCOREBOARD_URL, fightcenter]
