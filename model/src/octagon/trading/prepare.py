"""One-click 'generate predictions' for the event in the live feed.

Runs the same CLI steps as by hand (`fetch-card`, `fetch-odds`, `predict`) in
a background thread and subprocess. It never overwrites an existing card or
frozen predictions: an existing card is only predicted if its predictions are
missing, and a Wikipedia 'next event' card is accepted only when its fighters
match the live feed.

It also saves each card's day-before context (`fetch-context`) so that
`octagon score-context` can measure it later.
"""

from __future__ import annotations

import subprocess
import sys
import threading
from datetime import date
from pathlib import Path

import yaml

from octagon.scraping.fighters import slug
from octagon.trading.names import same_pair

STEP_TIMEOUT = 900
# Context is news and fan reaction. Fetched earlier than this it would be stale
# by fight night, so a card further out waits.
CONTEXT_DAYS_AHEAD = 1


class CardPreparer:
    def __init__(self, root: Path, scratch: Path):
        self.root, self.scratch = root, scratch
        self.lock = threading.Lock()
        self.state = {"state": "idle", "message": ""}
        # Cards whose context fetch was already started by this process.
        self.context_tried: set[str] = set()

    def status(self) -> dict:
        with self.lock:
            return dict(self.state)

    def start(self, event_name: str, pairs: list[tuple[str, str]]) -> dict:
        with self.lock:
            if self.state["state"] == "running":
                return dict(self.state)
            self.state = {"state": "running", "message": "Finding tonight's card…"}
        threading.Thread(target=self._run, args=(event_name, pairs), daemon=True).start()
        return self.status()

    def ensure_context(self, card_slug: str, card_date: str, today: date | None = None) -> None:
        """Save the card's day-before context once, in the background.

        News, YouTube comments and short-notice flags. The bot does not bet on
        them; `octagon score-context` measures later whether it should. The
        fetch has to happen before the fights, which is why it is automatic.
        """
        card = self.root / "cards" / f"{card_slug}.yaml"
        saved = self.root / "data" / "card_context" / f"{card_slug}.json"
        try:
            days_ahead = (date.fromisoformat(card_date[:10]) - (today or date.today())).days
        except ValueError:
            return
        if not 0 <= days_ahead <= CONTEXT_DAYS_AHEAD:
            return
        with self.lock:
            if card_slug in self.context_tried or saved.exists() or not card.exists():
                return
            self.context_tried.add(card_slug)
        threading.Thread(target=self._fetch_context, args=(card,), daemon=True).start()

    def _fetch_context(self, card: Path):
        try:
            self._octagon("fetch-context", "--card", str(card))
        except (subprocess.TimeoutExpired, OSError):
            pass  # measurement data only; the card trades without it

    def _set(self, state: str, message: str):
        with self.lock:
            self.state = {"state": state, "message": message}

    def _octagon(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-m", "octagon", *args], cwd=self.root,
                              capture_output=True, text=True, timeout=STEP_TIMEOUT)

    def _run(self, event_name: str, pairs: list[tuple[str, str]]):
        try:
            out = self.root / "cards" / (slug(event_name).replace("-", "_") + ".yaml")
            created = False
            if not out.exists():
                self._octagon("fetch-card", "--event", event_name,
                              "--date", date.today().isoformat(), "--out", str(out))
                created = out.exists()
            if out.exists() and not self._matches(out, pairs):
                if not created:
                    self._set("failed", f"{out.name} already exists for different fights; "
                                        "not overwriting it.")
                    return
                out.unlink()  # only the file this run just wrote
            if not out.exists():
                self.scratch.mkdir(parents=True, exist_ok=True)
                candidate = self.scratch / "next_card.yaml"
                candidate.unlink(missing_ok=True)  # never accept a stale earlier fetch
                self._octagon("fetch-card", "--out", str(candidate))
                if not candidate.exists() or not self._matches(candidate, pairs):
                    self._set("failed", "Couldn't find this event's fights on Wikipedia.")
                    return
                if not out.exists():
                    candidate.replace(out)
            predictions = self.root / "reports" / f"card_predictions_{out.stem}.parquet"
            if not predictions.exists():
                # A saved line is only the fallback for ESPN's live one, so a
                # missing API key or an unlisted fight is not a failure.
                self._set("running", "Looking up sportsbook lines…")
                self._octagon("fetch-odds", "--card", str(out), "--keep-existing")
                self._set("running", "Running the model on tonight's fights…")
                result = self._octagon("predict", "--card", str(out))
                if result.returncode != 0 or not predictions.exists():
                    self._set("failed", "The model could not predict this card. "
                                        "Run `octagon predict` by hand to see why.")
                    return
            self._set("done", "Predictions ready.")
        except subprocess.TimeoutExpired:
            self._set("failed", "Generating predictions took too long.")
        except Exception as exc:  # surfaced to the dashboard, never raised into the server
            self._set("failed", f"Generating predictions failed: {type(exc).__name__}")

    @staticmethod
    def _matches(card_path: Path, pairs: list[tuple[str, str]]) -> bool:
        try:
            card = yaml.safe_load(card_path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            return False
        bouts = [(f.get("fighter1", ""), f.get("fighter2", "")) for f in card.get("fights") or []]
        hits = sum(any(same_pair(b, p) for p in pairs) for b in bouts)
        return hits >= max(1, min(len(bouts), len(pairs)) // 2)
