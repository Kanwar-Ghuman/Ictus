"""One-click 'generate predictions' for the event in the live feed.

Runs the same CLI steps as by hand (`fetch-card`, then `predict`) in a
background thread and subprocess. It never overwrites an existing card or
frozen predictions: an existing card is only predicted if its predictions are
missing, and a Wikipedia 'next event' card is accepted only when its fighters
match the live feed.
"""

from __future__ import annotations

import subprocess
import sys
import threading
from datetime import date
from pathlib import Path

import yaml

from octagon.scraping.fighters import slug
from octagon.trading.autoplan import same_pair

STEP_TIMEOUT = 900


class CardPreparer:
    def __init__(self, root: Path, scratch: Path):
        self.root, self.scratch = root, scratch
        self.lock = threading.Lock()
        self.state = {"state": "idle", "message": ""}

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
