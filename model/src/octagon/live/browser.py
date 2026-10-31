"""Playwright interceptor for ESPN Fightcenter.

Prefer HttpCollector when ESPN answers a plain GET — it is faster. Use this
when the CDN starts blocking scripted HTTP (the cloud fetchers already 403).
The browser opens the same page a fan would, then we steal the XHR the page
already makes. We do not touch Paramount+ or any paywalled stream.
"""

from __future__ import annotations

import json
from typing import Any

from octagon.live.espn import parse_fightcenter
from octagon.live.schema import EventSnapshot

FIGHTCENTER_PAGE = "https://www.espn.com/mma/fightcenter/_/id/{event_id}/league/ufc"
FIGHTCENTER_MARK = "/apis/common/v3/sports/mma/ufc/fightcenter/"


class BrowserCollector:
    """Headless Chromium that intercepts ESPN's live fightcenter JSON."""

    source = "espn_fightcenter_browser"

    def __init__(
        self,
        event_id: str,
        headed: bool = False,
        timeout_ms: int = 20_000,
    ) -> None:
        if not event_id:
            raise ValueError("BrowserCollector needs an ESPN event id")
        self.event_id = event_id
        self.headed = headed
        self.timeout_ms = timeout_ms
        self._playwright = None
        self._browser = None
        self._page = None
        self._latest: dict[str, Any] | None = None

    def start(self) -> None:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright is not installed. "
                "Run: uv pip install playwright && playwright install chromium"
            ) from exc
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=not self.headed)
        self._page = self._browser.new_page()
        self._page.on("response", self._on_response)

    def close(self) -> None:
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()
        self._browser = None
        self._playwright = None
        self._page = None
        self._latest = None

    def snapshot(self) -> EventSnapshot:
        if self._page is None:
            self.start()
        payload = self._capture()
        return parse_fightcenter(payload)

    def _on_response(self, response: Any) -> None:
        if FIGHTCENTER_MARK not in response.url:
            return
        try:
            payload = response.json()
        except Exception:
            return
        if payload.get("cards"):
            self._latest = payload

    def _capture(self) -> dict[str, Any]:
        assert self._page is not None
        self._latest = None
        self._page.goto(
            FIGHTCENTER_PAGE.format(event_id=self.event_id),
            wait_until="domcontentloaded",
            timeout=self.timeout_ms,
        )
        self._page.wait_for_timeout(1500)
        if self._latest is None:
            raise RuntimeError("Playwright loaded Fightcenter but no JSON XHR arrived")
        return self._latest


def parse_intercepted_json(raw: str) -> EventSnapshot:
    """Used by tests so we can feed a captured XHR without launching Chromium."""
    return parse_fightcenter(json.loads(raw))
