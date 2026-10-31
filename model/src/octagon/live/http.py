"""Polite HTTP client for ESPN's public fightcenter JSON.

A browser User-Agent is required — ESPN's CDN 403s default Python clients.
This is the low-latency path: one JSON GET, no Chromium.
"""

from __future__ import annotations

from typing import Any

import requests

from octagon.live.espn import discover_event_id, parse_fightcenter
from octagon.live.schema import EventSnapshot

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/mma/ufc/scoreboard"
FIGHTCENTER_URL = (
    "https://site.web.api.espn.com/apis/common/v3/sports/mma/ufc/fightcenter/{event_id}"
)
FIGHTCENTER_PARAMS = {
    "region": "us",
    "lang": "en",
    "contentorigin": "espn",
}


class EspnHttpError(RuntimeError):
    """ESPN refused or returned a payload we cannot use."""


class HttpCollector:
    """Pull the live card over HTTP. Fastest source we found that is not paid."""

    source = "espn_fightcenter"

    def __init__(
        self,
        event_id: str | None = None,
        session: requests.Session | None = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        self.event_id = event_id
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds
        self.session.headers.setdefault("User-Agent", USER_AGENT)
        self.session.headers.setdefault("Accept", "application/json")

    def snapshot(self) -> EventSnapshot:
        event_id = self.event_id or self._discover()
        self.event_id = event_id
        payload = self._get_json(FIGHTCENTER_URL.format(event_id=event_id), FIGHTCENTER_PARAMS)
        if not payload.get("cards"):
            raise EspnHttpError(f"Fightcenter {event_id} had no cards")
        return parse_fightcenter(payload)

    def _discover(self) -> str:
        payload = self._get_json(SCOREBOARD_URL)
        event_id = discover_event_id(payload)
        if not event_id:
            raise EspnHttpError("ESPN scoreboard listed no UFC events")
        return event_id

    def _get_json(self, url: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        try:
            response = self.session.get(url, params=params, timeout=self.timeout_seconds)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            raise EspnHttpError(f"ESPN request failed: {exc}") from exc
